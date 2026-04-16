#!/usr/local/bin/python3
"""
sync_local_to_pod v2 — 本地目录同步到 K8s Pod
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ─── 常量 ──────────────────────────────────────────────────────────────────
REMOTE_TMP_TAR = "/tmp/sync_archive.tar.gz"
COMPRESS_FAST_PATH_THRESHOLD = 100   # 待上传文件数超过此值时切换为压缩上传


# ─── SyncConfig ─────────────────────────────────────────────────────────────

@dataclass
class SyncConfig:
    cluster: str
    namespace: str
    pod_label: str
    remote_parent_path: str
    local_path: str
    # 运行时计算字段
    remote_path: str = field(init=False)
    # 可选字段
    compress_threshold: int = 50
    max_workers: int = 10
    debug: bool = False
    show_concurrency: bool = False
    no_watch: bool = False
    skip_verify: bool = False
    debounce_seconds: float = 1.0
    exclude_paths: list = field(default_factory=list)

    def __post_init__(self):
        self.remote_path = os.path.join(
            self.remote_parent_path, os.path.basename(self.local_path)
        )

    @classmethod
    def from_dict(cls, d: dict) -> "SyncConfig":
        """从配置字典构造 SyncConfig，校验必填字段。"""
        required = ["cluster", "namespace", "pod_label", "remote_parent_path", "local_path"]
        missing = [f for f in required if not d.get(f)]
        if missing:
            raise ValueError(f"配置缺少必需字段: {', '.join(missing)}")
        return cls(
            cluster=d["cluster"],
            namespace=d["namespace"],
            pod_label=d["pod_label"],
            remote_parent_path=d["remote_parent_path"],
            local_path=d["local_path"],
            compress_threshold=d.get("compress_threshold", 50),
            max_workers=d.get("max_workers", 10),
            debug=d.get("debug", False),
            show_concurrency=d.get("show_concurrency", False),
            no_watch=d.get("no_watch", False),
            skip_verify=d.get("skip_verify", False),
            debounce_seconds=d.get("debounce_seconds", 1.0),
            exclude_paths=d.get("exclude_paths", []),
        )

# ─── 日志配置 ────────────────────────────────────────────────────────────────

def configure_logger(debug: bool = False) -> None:
    logger.remove()
    level = "DEBUG" if debug else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=level,
    )


# ─── Shell / kubectl 工具 ───────────────────────────────────────────────────

def run_cmd(
    command: str,
    *,
    debug: bool = False,
    desc: str = None,
    timeout: int = 600,
    retries: int = 0,
    retry_delay: float = 1.0,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """统一执行 shell 命令，支持超时、重试、统一错误日志。"""
    if debug:
        logger.debug(f"[cmd] {desc + ': ' if desc else ''}{command}")

    last_err = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=timeout, check=check,
            )
        except subprocess.TimeoutExpired as e:
            last_err = e
            logger.error(f"❌ 命令超时({timeout}s){' - ' + desc if desc else ''}: {command}")
        except subprocess.CalledProcessError as e:
            last_err = e
            stderr = (e.stderr or "").strip()
            msg = stderr or f"错误码: {e.returncode}"
            logger.error(f"❌ 命令失败{' - ' + desc if desc else ''}: {msg}")

        if attempt < retries:
            logger.warning(f"🔄 重试({attempt + 1}/{retries}){' - ' + desc if desc else ''}")
            time.sleep(retry_delay)

    if last_err:
        raise last_err
    raise RuntimeError("run_cmd: unexpected state")


def select_running_pod_by_label(cfg: SyncConfig) -> str:
    """通过 label 选择 running 状态的 pod，返回 pod name。失败时抛异常。"""
    cmd = (
        f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} '
        f'get pods -l {cfg.pod_label} '
        f'--field-selector=status.phase=Running '
        f'-o jsonpath="{{.items[0].metadata.name}}"'
    )
    result = run_cmd(cmd, debug=cfg.debug, desc="select running pod",
                     timeout=30, retries=2, retry_delay=1.0, check=True)
    pod_name = (result.stdout or "").strip().strip("'\"")
    if not pod_name:
        raise RuntimeError(
            f"未找到 running 状态的 pod (namespace={cfg.namespace}, label={cfg.pod_label})"
        )
    return pod_name


# ─── 文件工具 ────────────────────────────────────────────────────────────────

def is_excluded(rel_path: str, exclude_paths: list) -> bool:
    """判断相对路径是否匹配任一排除规则。"""
    for pattern in exclude_paths:
        if (rel_path == pattern
                or rel_path.startswith(pattern + os.sep)
                or rel_path.startswith(pattern + "/")):
            return True
    return False


def is_hidden(name: str) -> bool:
    """判断文件或目录名是否为隐藏（以 . 开头）。"""
    return name.startswith(".")


def calculate_file_md5(file_path: str) -> str | None:
    """计算文件 MD5，失败返回 None。"""
    h = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.error(f"计算 MD5 失败 {file_path}: {e}")
        return None


def format_file_size(size_bytes: int) -> str:
    """将字节数格式化为可读字符串（B / KB / MB / GB）。"""
    if size_bytes == 0:
        return "0 B"
    names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    return f"{round(size_bytes / math.pow(1024, i), 2)} {names[i]}"


def count_files(local_path: str, exclude_paths: list) -> int:
    """统计待同步文件数（排除隐藏文件和 exclude_paths）。"""
    count = 0
    for root, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if not is_hidden(d)]
        for name in files:
            if is_hidden(name):
                continue
            rel = os.path.relpath(os.path.join(root, name), local_path)
            if not is_excluded(rel, exclude_paths):
                count += 1
    return count


def compress_dir(src_dir: str, out_file: str, exclude_paths: list, debug: bool) -> None:
    """将 src_dir 压缩为 tar.gz，排除隐藏文件和 exclude_paths。"""
    files_to_compress = []

    logger.info("🔍 扫描待压缩文件...")
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if not is_hidden(d)]
        dirs[:] = [
            d for d in dirs
            if not is_excluded(os.path.relpath(os.path.join(root, d), src_dir), exclude_paths)
        ]
        for name in files:
            if is_hidden(name):
                continue
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, src_dir)
            if is_excluded(rel, exclude_paths):
                if debug:
                    logger.debug(f"排除: {rel}")
                continue
            try:
                files_to_compress.append((fp, rel, os.path.getsize(fp)))
            except Exception:
                pass

    if files_to_compress:
        logger.info("=" * 60)
        logger.info("📊 体积最大的 10 个文件:")
        logger.info("=" * 60)
        for idx, (_, rel, sz) in enumerate(
            sorted(files_to_compress, key=lambda x: x[2], reverse=True)[:10], 1
        ):
            logger.info(f"  {idx:2d}. {format_file_size(sz):>10s}  {rel}")
        logger.info("=" * 60)

    logger.info("📦 开始压缩文件...")
    with tarfile.open(out_file, "w:gz") as tar:
        for fp, rel, _ in files_to_compress:
            tar.add(fp, arcname=rel)
    logger.success(f"✅ 压缩完成: 已打包 {len(files_to_compress)} 个文件")


# ─── 远端操作 ────────────────────────────────────────────────────────────────

def is_remote_empty(cfg: SyncConfig, pod_name: str) -> bool:
    """快速判断远端目录是否没有任何文件。"""
    cmd = (
        f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} exec {pod_name} -- '
        f'bash -c "test -d {cfg.remote_path} && '
        f'find {cfg.remote_path} -type f -print -quit 2>/dev/null"'
    )
    result = run_cmd(cmd, debug=cfg.debug, desc="probe remote empty",
                     timeout=60, retries=0, check=False)
    return not bool((result.stdout or "").strip())


def get_remote_files_md5(cfg: SyncConfig, pod_name: str) -> dict:
    """获取远端所有文件的 {rel_path: md5} 映射（排除 exclude_paths）。"""
    cmd = (
        f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} exec {pod_name} -- '
        f'find {cfg.remote_path} -type f -exec md5sum {{}} \\; 2>/dev/null || echo ""'
    )
    result = run_cmd(cmd, debug=cfg.debug, desc="collect remote md5",
                     timeout=600, retries=0, check=False)

    remote_files = {}
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            md5_val, file_path = parts[0], " ".join(parts[1:])
            if not file_path.startswith(cfg.remote_path):
                continue
            rel = file_path[len(cfg.remote_path):].lstrip("/")
            if not is_excluded(rel, cfg.exclude_paths):
                remote_files[rel] = md5_val
    return remote_files


def compress_and_upload(
    cfg: SyncConfig, pod_name: str, tmp_dir: str, label: str = "同步"
) -> tuple[float, float, float]:
    """
    压缩本地目录 → 上传到 pod → 远端解压到 cfg.remote_path。
    返回 (compress_time, upload_time, extract_time)。
    失败时抛出 subprocess.CalledProcessError。
    """
    tar_path = os.path.join(tmp_dir, "sync_upload.tar.gz")

    # 1. 压缩
    logger.info("📦 正在压缩本地目录...")
    t0 = time.time()
    compress_dir(cfg.local_path, tar_path, cfg.exclude_paths, cfg.debug)
    compress_time = time.time() - t0
    logger.success(
        f"✅ 压缩完成: {format_file_size(os.path.getsize(tar_path))} (耗时: {compress_time:.2f}s)"
    )

    # 2. 上传
    remote_tar = os.path.join(cfg.remote_parent_path, "sync_upload.tar.gz")
    cmd_cp = (
        f"tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} "
        f"cp {tar_path} {pod_name}:{remote_tar}"
    )
    logger.info("📤 上传压缩包...")
    t0 = time.time()
    run_cmd(cmd_cp, debug=cfg.debug, desc=f"{label} upload",
            timeout=1800, retries=1, retry_delay=2.0, check=True)
    upload_time = time.time() - t0
    logger.success(f"✅ 上传完成 (耗时: {upload_time:.2f}s)")

    # 3. 远端解压（先 mkdir，再清空，再解压，最后删临时包）
    cmd_extract = (
        f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} exec {pod_name} -- '
        f'bash -c "mkdir -p {cfg.remote_path} && '
        f'rm -rf {cfg.remote_path}/* && '
        f'tar -xzf {remote_tar} -C {cfg.remote_path} && '
        f'rm {remote_tar}"'
    )
    logger.info("📦 远端解压...")
    t0 = time.time()
    run_cmd(cmd_extract, debug=cfg.debug, desc=f"{label} extract",
            timeout=1800, retries=0, check=True)
    extract_time = time.time() - t0
    logger.success(f"✅ 解压完成 (耗时: {extract_time:.2f}s)")

    return compress_time, upload_time, extract_time


# ─── 初始同步 ────────────────────────────────────────────────────────────────

def _log_timing(label: str, compress_time: float, upload_time: float,
                extract_time: float, total_time: float) -> None:
    logger.info("\n" + "=" * 60)
    logger.info(f"⏱️  {label}耗时统计")
    logger.info("=" * 60)
    logger.info(f"  1. 压缩文件:   {compress_time:.2f}s")
    logger.info(f"  2. 上传文件:   {upload_time:.2f}s")
    logger.info(f"  3. 远端解压:   {extract_time:.2f}s")
    logger.info(f"  总耗时:        {total_time:.2f}s")
    logger.info("=" * 60)


def upload_initial_files(cfg: SyncConfig, pod_name: str) -> None:
    """初始上传：远端空→直接压缩上传；否则 MD5 对比，文件多则压缩快速路径，少则逐文件上传。"""
    start = time.time()

    # 确保远端目录存在
    ensure_cmd = (
        f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} '
        f'exec {pod_name} -- bash -c "mkdir -p {cfg.remote_path}"'
    )
    try:
        run_cmd(ensure_cmd, debug=cfg.debug, desc="ensure remote dir",
                timeout=120, retries=1, retry_delay=1.0, check=True)
    except subprocess.CalledProcessError:
        logger.error("❌ 确保远程目录失败")
        return

    # 远端空探测
    logger.info("🔎 检查远程目录...")
    if is_remote_empty(cfg, pod_name):
        logger.info("远端为空，直接压缩上传...")
        with tempfile.TemporaryDirectory() as tmp:
            ct, ut, et = compress_and_upload(cfg, pod_name, tmp, label="首次")
        _log_timing("首次压缩同步", ct, ut, et, time.time() - start)
        logger.success("🎉 首次同步完成！开始文件变更监听...")
        return

    # MD5 对比
    logger.info("获取远程文件 MD5 值...")
    remote_md5 = get_remote_files_md5(cfg, pod_name)
    logger.info(f"远程文件数量: {len(remote_md5)}")

    # 收集待上传文件
    files_to_upload = []
    files_skipped = 0
    dirs_needed: set = set()

    for root, dirs, files in os.walk(cfg.local_path):
        dirs[:] = [d for d in dirs if not is_hidden(d)]
        for name in files:
            if is_hidden(name):
                continue
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, cfg.local_path)
            if is_excluded(rel, cfg.exclude_paths):
                continue
            local_md5 = calculate_file_md5(fp)
            if rel in remote_md5 and local_md5 == remote_md5[rel]:
                files_skipped += 1
                continue
            dirs_needed.add(os.path.dirname(os.path.join(cfg.remote_path, rel)))
            files_to_upload.append((fp, rel))

    logger.info(
        f"📊 清单汇总 -> 远程: {len(remote_md5)} | "
        f"本地: {files_skipped + len(files_to_upload)} | "
        f"待上传: {len(files_to_upload)}"
    )

    # 文件多 → 压缩快速路径
    if len(files_to_upload) > COMPRESS_FAST_PATH_THRESHOLD:
        logger.info(f"🗜️  待上传文件数 > {COMPRESS_FAST_PATH_THRESHOLD}，切换为压缩快速路径...")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ct, ut, et = compress_and_upload(cfg, pod_name, tmp, label="快速")
            _log_timing("快速压缩同步", ct, ut, et, time.time() - start)
            logger.success("🎉 初始同步完成！开始文件变更监听...")
            return
        except subprocess.CalledProcessError:
            logger.error("❌ 压缩快速路径失败，回退到增量上传")

    if not files_to_upload:
        logger.info("无文件需要上传")
        logger.success("🎉 初始同步完成（无变更）！开始文件变更监听...")
        return

    # 批量创建目录
    _batch_mkdir(cfg, pod_name, dirs_needed)

    # 逐文件并发上传
    _concurrent_upload(cfg, pod_name, files_to_upload)

    logger.info(f"\n⏱️  初始同步完成，总耗时: {time.time() - start:.2f}s")
    logger.success("🎉 初始同步完成！开始文件变更监听...")


def _batch_mkdir(cfg: SyncConfig, pod_name: str, dirs: set) -> None:
    """批量在远端创建目录（去冗余后一次 exec）。"""
    if not dirs:
        return
    sorted_dirs = sorted(dirs)
    # 去掉被其他目录覆盖的父目录
    leaf_dirs = [
        d for d in sorted_dirs
        if not any(other != d and other.startswith(d + "/") for other in sorted_dirs)
    ]
    cmd = (
        f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} '
        f'exec {pod_name} -- mkdir -p {" ".join(leaf_dirs)}'
    )
    try:
        run_cmd(cmd, debug=cfg.debug, desc="mkdir remote dirs",
                timeout=300, retries=1, retry_delay=1.0, check=True)
        logger.success(f"✅ 目录创建成功: {len(leaf_dirs)} 个")
    except subprocess.CalledProcessError:
        logger.error("❌ 目录创建失败")


def _concurrent_upload(cfg: SyncConfig, pod_name: str,
                        files_to_upload: list) -> None:
    """多线程并发上传文件列表。"""
    total = len(files_to_upload)
    completed = 0
    lock = threading.Lock()

    def upload_one(file_info):
        nonlocal completed
        fp, rel = file_info
        sz = format_file_size(os.path.getsize(fp))
        cmd = (
            f'tess kubectl --cluster {cfg.cluster} -n {cfg.namespace} '
            f'cp {fp} {pod_name}:{os.path.join(cfg.remote_path, rel)}'
        )
        t0 = time.time()
        for attempt in range(3):
            try:
                run_cmd(cmd, debug=cfg.debug, desc=f"upload {rel}",
                        timeout=1800, retries=0, check=True)
                elapsed = time.time() - t0
                with lock:
                    completed += 1
                    pct = completed / total * 100
                    retry_note = f" (重试{attempt}次)" if attempt else ""
                    logger.success(
                        f"✅ {rel} ({sz}, {elapsed:.2f}s{retry_note}) [{pct:.1f}%]"
                    )
                return True
            except subprocess.CalledProcessError:
                if attempt < 2:
                    logger.warning(f"🔄 重试 {rel} ({attempt + 1}/3)")
        with lock:
            completed += 1
        logger.error(f"❌ 上传失败（3次）: {rel}")
        return False

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
        futures = {ex.submit(upload_one, f): f for f in files_to_upload}
        ok = sum(1 for fut in futures if fut.result())
        fail = total - ok
    logger.info(f"📊 上传统计: ✅ {ok} 成功, ❌ {fail} 失败")


# ─── 文件监听 ────────────────────────────────────────────────────────────────

_TEMP_SUFFIXES = ("~", ".swp", ".swo", ".swn", ".tmp", ".bak", ".temp")
_TEMP_PREFIXES = (".#", "~")


def _is_temp_file(name: str) -> bool:
    return (
        any(name.endswith(s) for s in _TEMP_SUFFIXES)
        or any(name.startswith(p) for p in _TEMP_PREFIXES)
        or ".tmp." in name
        or name.endswith("#")
    )


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, cfg: SyncConfig, pod_name: str, executor: ThreadPoolExecutor):
        self.cfg = cfg
        self.pod_name = pod_name
        self.executor = executor
        self.processing_files: dict = {}
        self.debounce_timers: dict = {}
        self.pending_uploads: dict = {}

    # ── 事件过滤 ────────────────────────────────────────────────────────────

    def _should_skip(self, path: str) -> bool:
        name = os.path.basename(path)
        if any(part.startswith(".") for part in path.split(os.sep)):
            return True
        if _is_temp_file(name):
            return True
        rel = os.path.relpath(path, self.cfg.local_path)
        return is_excluded(rel, self.cfg.exclude_paths)

    # ── watchdog 回调 ────────────────────────────────────────────────────────

    def on_modified(self, event):
        if event.is_directory:
            return
        if self.cfg.debug:
            logger.debug(f"[监听] modified: {event.src_path}")
        if not self._should_skip(event.src_path):
            self.upload_file(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        if self.cfg.debug:
            logger.debug(f"[监听] created: {event.src_path}")
        if not self._should_skip(event.src_path):
            self.upload_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if self.cfg.debug:
            logger.debug(f"[监听] moved: {event.src_path} -> {event.dest_path}")
        dest = event.dest_path
        if dest.startswith(self.cfg.local_path) and not self._should_skip(dest):
            self.upload_file(dest)

    # ── 防抖上传 ─────────────────────────────────────────────────────────────

    def upload_file(self, file_path: str) -> None:
        rel = os.path.relpath(file_path, self.cfg.local_path)
        # 如果正在上传，打标记等完成后再触发
        fut = self.processing_files.get(file_path)
        if fut and not fut.done():
            self.pending_uploads[file_path] = True
            if self.cfg.debug:
                logger.debug(f"正在上传，打待上传标记: {rel}")
            return

        # 取消旧防抖定时器
        old_timer = self.debounce_timers.pop(file_path, None)
        if old_timer and old_timer.is_alive():
            old_timer.cancel()

        logger.info(
            f"🔍 检测到文件变更: {rel} "
            f"(将在 {self.cfg.debounce_seconds}s 后上传)"
        )
        timer = threading.Timer(
            self.cfg.debounce_seconds, self._debounced_upload, args=[file_path]
        )
        self.debounce_timers[file_path] = timer
        timer.start()

    def _debounced_upload(self, file_path: str) -> None:
        self.debounce_timers.pop(file_path, None)
        fut = self.processing_files.get(file_path)
        if fut and not fut.done():
            self.pending_uploads[file_path] = True
            return
        self.processing_files[file_path] = self.executor.submit(
            self._upload_file, file_path
        )

    def _upload_file(self, file_path: str) -> None:
        rel = os.path.relpath(file_path, self.cfg.local_path)
        start = time.time()
        try:
            # 确保远端目录
            remote_dir = os.path.dirname(
                os.path.join(self.cfg.remote_path, rel)
            )
            mkdir_cmd = (
                f'tess kubectl --cluster {self.cfg.cluster} '
                f'-n {self.cfg.namespace} exec {self.pod_name} -- mkdir -p {remote_dir}'
            )
            try:
                run_cmd(mkdir_cmd, debug=self.cfg.debug, desc=f"mkdir {remote_dir}",
                        timeout=120, retries=1, retry_delay=1.0, check=True)
            except subprocess.CalledProcessError:
                logger.error(f"❌ 创建远程目录失败: {remote_dir}")

            sz = format_file_size(os.path.getsize(file_path))
            cmd = (
                f'tess kubectl --cluster {self.cfg.cluster} '
                f'-n {self.cfg.namespace} cp {file_path} '
                f'{self.pod_name}:{os.path.join(self.cfg.remote_path, rel)}'
            )
            run_cmd(cmd, debug=self.cfg.debug, desc=f"realtime upload {rel}",
                    timeout=1800, retries=2, retry_delay=1.0, check=True)
            logger.success(
                f"✅ 文件同步成功: {rel} ({sz}, {time.time() - start:.2f}s) [实时同步]"
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                f"❌ 文件同步失败: {rel} - 错误码: {e.returncode} "
                f"(耗时: {time.time() - start:.2f}s)"
            )
        finally:
            self.processing_files.pop(file_path, None)
            if self.pending_uploads.pop(file_path, False):
                rel = os.path.relpath(file_path, self.cfg.local_path)
                logger.info(f"🔄 检测到新变更，将在 {self.cfg.debounce_seconds}s 后重新上传: {rel}")
                timer = threading.Timer(
                    self.cfg.debounce_seconds, self._debounced_upload, args=[file_path]
                )
                self.debounce_timers[file_path] = timer
                timer.start()


# ─── 配置管理 ────────────────────────────────────────────────────────────────

def get_config_path(project_name: str) -> Path:
    config_dir = Path.home() / ".sync2pod" / project_name
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "sync_config.json"


def load_config(project_name: str) -> dict:
    path = get_config_path(project_name)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_config(project_name: str, config: dict) -> None:
    with open(get_config_path(project_name), "w") as f:
        json.dump(config, f, indent=4)


def list_projects() -> None:
    sync2pod_dir = Path.home() / ".sync2pod"
    if not sync2pod_dir.exists():
        logger.info("📋 没有找到任何项目配置")
        logger.info("  初始化: sync_local_to_pod --init-config --local-path <本地路径>")
        return

    projects = []
    for d in sync2pod_dir.iterdir():
        cfg_file = d / "sync_config.json"
        if d.is_dir() and cfg_file.exists():
            try:
                with open(cfg_file) as f:
                    cfg = json.load(f)
                projects.append({
                    "name": d.name,
                    "local_path": cfg.get("local_path", "N/A"),
                    "remote_parent_path": cfg.get("remote_parent_path", "N/A"),
                    "cluster": cfg.get("cluster", "N/A"),
                    "namespace": cfg.get("namespace", "N/A"),
                })
            except Exception:
                pass

    if not projects:
        logger.info("📋 没有找到任何有效的项目配置")
        return

    logger.info("=" * 60)
    logger.info(f"📋 已配置的项目 (共 {len(projects)} 个)")
    logger.info("=" * 60)
    for i, p in enumerate(projects, 1):
        logger.info(f"\n{i}. 项目名: {p['name']}")
        logger.info(f"   本地路径: {p['local_path']}")
        logger.info(f"   远程路径: {p['remote_parent_path']}")
        logger.info(f"   集群: {p['cluster']}  命名空间: {p['namespace']}")
    logger.info("\n" + "=" * 60)
    logger.info("  sync_local_to_pod --project <项目名>")
    logger.info("=" * 60)


_EXAMPLE_CONFIG = {
    "cluster": "908",
    "namespace": "sdsnushare01-dev",
    "pod_label": "serviceName=hk-develop",
    "remote_parent_path": "/mnt/gfs-develop/workspace",
    "local_path": "__REPLACE__",
    "compress_threshold": 50,
    "max_workers": 10,
    "debug": False,
    "show_concurrency": False,
    "no_watch": False,
    "skip_verify": False,
    "debounce_seconds": 1.0,
    "exclude_paths": ["node_modules", "*.log", "dist/build"],
}


def init_config(project_name: str, local_path: str) -> None:
    config_path = get_config_path(project_name)

    if config_path.exists():
        cfg = load_config(project_name)
        if not cfg.get("local_path"):
            cfg["local_path"] = local_path
            save_config(project_name, cfg)
            logger.success("✅ 配置文件已更新（添加 local_path）")
        else:
            logger.info("⚠️  配置文件已存在")
        logger.info(f"📁 {config_path}")
        logger.info(f"  vim {config_path}")
        logger.info(f"  sync_local_to_pod --project {project_name}")
        return

    example = {**_EXAMPLE_CONFIG, "local_path": local_path}
    save_config(project_name, example)
    logger.success("✅ 配置文件已创建")
    logger.info(f"📁 {config_path}")
    logger.info(json.dumps(example, indent=4, ensure_ascii=False))
    logger.info(f"  vim {config_path}")
    logger.info(f"  sync_local_to_pod --project {project_name}")


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def _run_sync(project_name: str, force_full_sync: bool, skip_verify_flag: bool) -> None:
    """加载配置、确认、选 Pod、执行同步+监听。"""
    config_path = get_config_path(project_name)
    raw = load_config(project_name)

    try:
        cfg = SyncConfig.from_dict(raw)
    except ValueError as e:
        logger.error(f"❌ {e}")
        logger.info(f"请编辑配置文件: {config_path}")
        sys.exit(1)

    # 命令行 skip_verify 优先于配置文件
    if skip_verify_flag:
        cfg.skip_verify = True

    configure_logger(cfg.debug)

    if not cfg.skip_verify:
        logger.info("=" * 60)
        logger.info("⚠️  同步前配置确认")
        logger.info("=" * 60)
        logger.info(f"配置文件:             {config_path}")
        logger.info(f"集群 (cluster):       {cfg.cluster}")
        logger.info(f"命名空间 (namespace): {cfg.namespace}")
        logger.info(f"Pod 标签 (pod_label): {cfg.pod_label}")
        logger.info(f"远程父目录:           {cfg.remote_parent_path}")
        logger.info(f"实际同步目录:         {cfg.remote_path}")
        logger.info(f"本地路径:             {cfg.local_path}")
        logger.info("=" * 60)
        logger.info("⚠️  确认无误后按回车继续（Ctrl+C 取消）...")
        try:
            input()
        except KeyboardInterrupt:
            logger.error("\n❌ 用户取消同步")
            sys.exit(0)
        logger.success("✅ 确认完成，开始同步...\n")

    if not os.path.exists(cfg.local_path):
        logger.error(f"❌ 本地路径不存在: {cfg.local_path}")
        sys.exit(1)

    try:
        pod_name = select_running_pod_by_label(cfg)
    except Exception as e:
        logger.error(f"❌ 选择 Pod 失败: {e}")
        sys.exit(1)
    logger.info(f"🎯 目标 Pod: {pod_name}")

    # ── 同步 ──────────────────────────────────────────────────────────────
    if force_full_sync:
        logger.info("🗜️  强制全量同步模式...")
        t0 = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                ct, ut, et = compress_and_upload(cfg, pod_name, tmp, label="强制全量")
            except subprocess.CalledProcessError:
                logger.error("❌ 强制全量同步失败")
                sys.exit(1)
        _log_timing("强制全量同步", ct, ut, et, time.time() - t0)
    else:
        file_count = count_files(cfg.local_path, cfg.exclude_paths)
        logger.info(f"📊 本地文件数: {file_count}，开始 MD5 对比增量同步...")
        upload_initial_files(cfg, pod_name)

    # ── 文件监听 ──────────────────────────────────────────────────────────
    if cfg.no_watch:
        logger.success("✅ 同步完成（文件监听已禁用）")
        return

    logger.info(f"👀 启动文件变更监听... (并发: {cfg.max_workers}, 防抖: {cfg.debounce_seconds}s)")
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        handler = FileChangeHandler(cfg, pod_name, executor)
        observer = Observer()
        observer.schedule(handler, path=cfg.local_path, recursive=True)
        observer.start()
        logger.success(f"✅ 监听已启动: {cfg.local_path}")
        logger.info("   按 Ctrl+C 停止监听")
        try:
            while True:
                time.sleep(30)
                if cfg.show_concurrency:
                    active = len([f for f in handler.processing_files.values() if not f.done()])
                    if active:
                        logger.info(f"⚙️  活跃上传任务: {active}/{cfg.max_workers}")
        except KeyboardInterrupt:
            logger.info("\n⏹️  停止文件监听...")
            observer.stop()
        observer.join()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="本地目录同步到 K8s Pod",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  sync_local_to_pod --init-config --local-path /path/to/project
  sync_local_to_pod --list-projects
  sync_local_to_pod --project heketi
  sync_local_to_pod --project heketi --force
        """,
    )
    parser.add_argument("--init-config", action="store_true", help="初始化配置文件（需配合 --local-path）")
    parser.add_argument("--list-projects", action="store_true", help="列出所有已配置的项目")
    parser.add_argument("--project", help="项目名称")
    parser.add_argument("--local-path", help="本地目录路径（仅用于初始化）")
    parser.add_argument("--force", action="store_true", help="强制全量同步")
    parser.add_argument("--skip-verify", action="store_true", help="跳过同步前配置确认")
    args = parser.parse_args()

    configure_logger(debug=False)

    if args.list_projects:
        list_projects()
        return

    if args.init_config:
        if not args.local_path:
            logger.error("❌ --init-config 需要配合 --local-path 使用")
            sys.exit(1)
        local_path = os.path.abspath(args.local_path)
        if not os.path.exists(local_path):
            logger.error(f"❌ 本地路径不存在: {local_path}")
            sys.exit(1)
        init_config(os.path.basename(os.path.normpath(local_path)), local_path)
        return

    if not args.project:
        logger.error("❌ 请指定操作模式")
        logger.info("  初始化:   sync_local_to_pod --init-config --local-path <路径>")
        logger.info("  查看项目: sync_local_to_pod --list-projects")
        logger.info("  同步:     sync_local_to_pod --project <项目名>")
        sys.exit(1)

    project_name = args.project
    if os.path.isabs(project_name) or "/" in project_name:
        logger.error("❌ --project 应传入项目名称，而非路径")
        sys.exit(1)

    # 验证项目存在
    sync2pod_dir = Path.home() / ".sync2pod"
    existing = [
        d.name for d in sync2pod_dir.iterdir()
        if d.is_dir() and (d / "sync_config.json").exists()
    ] if sync2pod_dir.exists() else []

    if project_name not in existing:
        logger.error(f"❌ 项目 '{project_name}' 不存在")
        if existing:
            for p in existing:
                logger.info(f"  - {p}")
        else:
            logger.info("  初始化: sync_local_to_pod --init-config --local-path <路径>")
        sys.exit(1)

    _run_sync(project_name, force_full_sync=args.force, skip_verify_flag=args.skip_verify)


if __name__ == "__main__":
    main()
