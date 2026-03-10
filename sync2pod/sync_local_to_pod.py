#!/usr/local/bin/python3
"""
优化版 sync_local_to_pod 脚本
- 支持通过 pod label 自动选择 running pod
- 支持 --compress-threshold（默认50，配置文件持久化）
- 支持 --force-full-sync 强制全量同步
- 配置文件存储于 ~/.sync2pod/$project_name/sync_config.json
- MD5 对比增量同步
- 实时文件监听（watchdog）
- 多线程并发上传
- 进度与耗时展示
"""
import argparse
import os
import sys
import json
import tarfile
import tempfile
import shutil
import hashlib
import time
import subprocess
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from concurrent.futures import ThreadPoolExecutor
from loguru import logger


# ========== 子进程执行封装 ==========

def run_cmd(command, *, debug=False, desc=None, timeout=600, retries=0, retry_delay=1.0, check=True):
    """统一执行命令（主要用于 tess kubectl / 本地命令）。

    - command: str（当前脚本仍大量使用 shell 字符，先收敛到这里，后续再逐步去 shell=True）
    - timeout: 秒
    - retries: 失败重试次数（0 表示不重试）
    - check: True 则失败抛 CalledProcessError

    返回 subprocess.CompletedProcess
    """
    if desc:
        logger.debug(f"[cmd] {desc}: {command}") if debug else None
    elif debug:
        logger.debug(f"[cmd] {command}")

    last_err = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        except subprocess.TimeoutExpired as e:
            last_err = e
            logger.error(f"❌ 命令超时({timeout}s){' - ' + desc if desc else ''}: {command}")
        except subprocess.CalledProcessError as e:
            last_err = e
            stderr = (e.stderr or '').strip()
            if stderr:
                logger.error(f"❌ 命令执行错误{(' - ' + desc) if desc else ''}: {stderr}")
            else:
                logger.error(f"❌ 命令执行失败{(' - ' + desc) if desc else ''} (错误码: {e.returncode})")

        if attempt < retries:
            logger.warning(f"🔄 重试命令({attempt + 1}/{retries}){(' - ' + desc) if desc else ''}")
            time.sleep(retry_delay)

    # retries 用尽，抛出最后一次异常，便于上层决定回退/退出
    if last_err:
        raise last_err
    raise RuntimeError("run_cmd: unexpected state")


# ========== 日志配置 ==========

def configure_logger(debug=False):
    """配置 loguru 日志"""
    # 移除默认的 handler
    logger.remove()

    # 添加控制台输出
    if debug:
        # Debug 模式：显示详细信息（包含DEBUG级别日志）
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="DEBUG"
        )
    else:
        # 普通模式：显示时间、级别和消息（INFO及以上）
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO"
        )

    # 添加文件日志（可选）
    # logger.add("sync2pod_{time}.log", rotation="10 MB", retention="7 days", level="DEBUG")


# ========== 配置管理 ==========

def get_config_path(project_name):
    home = Path.home()
    print(f"home: {home}")
    config_dir = home / '.sync2pod' / project_name
    print(f"config_dir: {config_dir}")

    config_dir.mkdir(parents=True, exist_ok=True)
    # 修改为非隐藏文件名
    return config_dir / 'sync_config.json'


def load_config(project_name):
    config_path = get_config_path(project_name)
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        config = {}
    # 默认字段
    config.setdefault('compress_threshold', 50)
    return config


def save_config(project_name, config):
    config_path = get_config_path(project_name)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)


# ========== K8s Pod 选择逻辑 ==========

def select_running_pod_by_label(cluster, namespace, pod_label, debug=False):
    """通过 label 选择 running 状态的 pod，返回 pod name。

    说明：
    - 这里统一使用 run_cmd，获得一致的 debug/超时/重试/错误输出。
    - 失败时抛出异常，由主流程决定是否退出。

    返回：pod_name(str)
    """
    label_selector = pod_label
    jsonpath = "{.items[0].metadata.name}"

    # 注意：jsonpath 里不需要额外的引号，避免输出带单引号导致 strip 逻辑复杂
    cmd = (
        f"tess kubectl --cluster {cluster} "
        f"-n {namespace} "
        f"get pods "
        f"-l {label_selector} "
        f"--field-selector=status.phase=Running "
        f"-o jsonpath=\"{jsonpath}\""
    )

    # kubectl 偶发返回空（pod 正在重建），轻量重试两次
    result = run_cmd(cmd, debug=debug, desc="select running pod", timeout=30, retries=2, retry_delay=1.0, check=True)
    pod_name = (result.stdout or "").strip().strip("'\"").strip()

    if not pod_name:
        raise RuntimeError(f"未找到 running 状态的 pod (namespace={namespace}, label={pod_label})")

    return pod_name


# ========== 工具函数 ==========

def get_config_path(project_name):
    """获取项目配置文件的路径"""
    home = Path.home()
    config_dir = home / '.sync2pod' / project_name
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / 'sync_config.json'


def calculate_file_md5(file_path):
    """计算文件的 MD5 哈希值"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"计算 MD5 失败 {file_path}: {e}")
        return None


def format_file_size(size_bytes):
    """格式化文件大小显示"""
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


# ========== 文件同步逻辑 ==========

def count_files(local_path, exclude_paths=None):
    """统计需要同步的文件数量（排除隐藏文件）"""
    cnt = 0
    for root, dirs, files in os.walk(local_path):
        # 排除隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            # 跳过隐藏文件
            if file.startswith('.'):
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, local_path)

            # 检查是否在排除路径中
            should_exclude = False
            if exclude_paths:
                for exclude_path in exclude_paths:
                    if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(
                            exclude_path + '/'):
                        should_exclude = True
                        break

            if not should_exclude:
                cnt += 1

    return cnt


def compress_dir(src_dir, out_file, exclude_paths=None, debug=False):
    """压缩目录为 tar.gz 文件（排除隐藏文件和 exclude_paths 中的目录）"""
    if exclude_paths is None:
        exclude_paths = []

    # 第一步：收集所有待压缩的文件信息
    files_to_compress = []  # 存储 (file_path, rel_path, file_size)

    logger.info("🔍 扫描待压缩文件...")
    for root, dirs, files in os.walk(src_dir):
        # 排除隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        # 排除 exclude_paths 中的目录（直接修改 dirs 列表，避免遍历这些目录）
        dirs_to_remove = []
        for d in dirs:
            dir_path = os.path.join(root, d)
            rel_dir_path = os.path.relpath(dir_path, src_dir)

            for exclude_path in exclude_paths:
                # 检查目录是否匹配排除模式
                if rel_dir_path == exclude_path or rel_dir_path.startswith(
                        exclude_path + os.sep) or rel_dir_path.startswith(exclude_path + '/'):
                    dirs_to_remove.append(d)
                    if debug:
                        logger.debug(f'排除目录: {rel_dir_path}')
                    break

        # 从 dirs 列表中移除需要排除的目录，os.walk 将不会遍历这些目录
        for d in dirs_to_remove:
            dirs.remove(d)

        for file in files:
            # 跳过隐藏文件
            if file.startswith('.'):
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, src_dir)

            # 检查文件是否应排除
            should_exclude = False
            for exclude_path in exclude_paths:
                if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(
                        exclude_path + '/'):
                    should_exclude = True
                    if debug:
                        logger.debug(f'排除文件: {rel_path}')
                    break

            if not should_exclude:
                try:
                    file_size = os.path.getsize(file_path)
                    files_to_compress.append((file_path, rel_path, file_size))
                except Exception as e:
                    if debug:
                        logger.debug(f'获取文件大小失败 {rel_path}: {e}')

    # 第二步：显示最大的10个文件
    if files_to_compress:
        logger.info("\n" + "=" * 60)
        logger.info("📊 体积最大的 10 个文件:")
        logger.info("=" * 60)
        sorted_files = sorted(files_to_compress, key=lambda x: x[2], reverse=True)[:10]
        for idx, (_, rel_path, size) in enumerate(sorted_files, 1):
            size_str = format_file_size(size)
            logger.info(f"  {idx:2d}. {size_str:>10s}  {rel_path}")
        logger.info("=" * 60 + "\n")

    # 第三步：压缩文件
    logger.info("📦 开始压缩文件...")
    added_count = 0
    with tarfile.open(out_file, 'w:gz') as tar:
        for file_path, rel_path, _ in files_to_compress:
            tar.add(file_path, arcname=rel_path)
            added_count += 1

    logger.success(f'✅ 压缩完成: 已打包 {added_count} 个文件')


def is_remote_empty(pod_name, namespace, cluster, remote_path, debug=False):
    """快速判断远端目录是否为空（是否存在至少一个普通文件）。

    目的：避免首次同步时远端为空但仍执行 find+md5sum 全量扫描。

    返回：True 表示远端没有任何文件；False 表示至少存在一个文件。
    """
    cmd = (
        f"tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- "
        f"bash -c \"test -d {remote_path} && find {remote_path} -type f -print -quit 2>/dev/null\""
    )
    result = run_cmd(cmd, debug=debug, desc="probe remote empty", timeout=60, retries=0, check=False)
    return not bool((result.stdout or "").strip())


def get_remote_files_md5(pod_name, namespace, cluster, remote_path, debug=False, exclude_paths=None):
    """获取 Pod 中所有文件的 MD5 值（排除 exclude_paths）"""
    if exclude_paths is None:
        exclude_paths = []

    remote_files = {}
    try:
        command = (
            f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- '
            f'find {remote_path} -type f -exec md5sum {{}} \\; 2>/dev/null || echo ""'
        )
        result = run_cmd(command, debug=debug, desc="collect remote md5", timeout=600, retries=0, check=False)

        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        md5_value = parts[0]
                        file_path = ' '.join(parts[1:])
                        if file_path.startswith(remote_path):
                            rel_path = file_path[len(remote_path):].lstrip('/')

                            should_exclude = False
                            for exclude_path in exclude_paths:
                                if rel_path == exclude_path or rel_path.startswith(
                                        exclude_path + os.sep) or rel_path.startswith(exclude_path + '/'):
                                    should_exclude = True
                                    if debug:
                                        logger.debug(f'排除远程文件: {rel_path} (匹配排除模式: {exclude_path})')
                                    break

                            if not should_exclude:
                                remote_files[rel_path] = md5_value
                                if debug:
                                    logger.debug(f'远程文件: {rel_path} -> {md5_value}')
    except Exception as e:
        logger.error(f"获取远程文件 MD5 失败: {e}")

    return remote_files


def upload_initial_files(local_path, namespace, pod_name, remote_path, cluster, debug=False, max_workers=10,
                         exclude_paths=None):
    """初始上传：MD5 对比后仅上传有变化的文件。若远端为空，直接压缩上传。"""
    start_time = time.time()
    if exclude_paths is None:
        exclude_paths = []

    logger.info("🔎 检查远程目录并收集远程清单...")
    ensure_dir_cmd = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- bash -c "mkdir -p {remote_path}"'
    try:
        run_cmd(ensure_dir_cmd, debug=debug, desc="ensure remote dir", timeout=120, retries=1, retry_delay=1.0,
                check=True)
    except subprocess.CalledProcessError:
        # run_cmd 已打印 stderr
        logger.error("❌ 确保远程目录失败")
        return

    # 先做远端空探测：空则直接走压缩上传
    if is_remote_empty(pod_name, namespace, cluster, remote_path, debug=debug):
        logger.info("远端为空（快速探测），直接压缩上传，无需远端MD5扫描/本地MD5对比...")
        # 复用下面原有“远端为空”压缩上传逻辑：通过构造一个空的 remote_files_md5 进入分支
        remote_files_md5 = {}
        logger.info(f"远程文件数量: {len(remote_files_md5)}")
    else:
        logger.info("获取远程文件 MD5 值...")
        remote_files_md5 = get_remote_files_md5(pod_name, namespace, cluster, remote_path, debug, exclude_paths)
        logger.info(f"远程文件数量: {len(remote_files_md5)}")

    # 远端为空：无需本地MD5对比，直接压缩上传
    if len(remote_files_md5) == 0:
        logger.info("远端为空，直接压缩上传，无需本地MD5对比...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = os.path.join(tmp_dir, 'sync_upload.tar.gz')
            logger.info("📦 正在创建压缩包...")
            compress_start = time.time()
            compress_dir(local_path, tar_path, exclude_paths, debug)
            compress_end = time.time()
            compress_time = compress_end - compress_start

            compressed_size = os.path.getsize(tar_path)
            logger.success(f"✅ 压缩完成: {format_file_size(compressed_size)} (耗时: {compress_time:.2f}s)")

            remote_tmp_tar = "/tmp/sync_archive.tar.gz"
            upload_cmd = f'tess kubectl --cluster {cluster} -n {namespace} cp {tar_path} {pod_name}:{remote_tmp_tar}'
            logger.info("📤 上传压缩包到 Pod /tmp...")
            upload_start = time.time()
            try:
                run_cmd(upload_cmd, debug=debug, desc="upload archive", timeout=1800, retries=1, retry_delay=2.0,
                        check=True)
            except subprocess.CalledProcessError:
                logger.error("❌ 压缩包上传失败")
                return
            upload_end = time.time()
            upload_time = upload_end - upload_start
            logger.success(f"✅ 压缩包上传成功 (耗时: {upload_time:.2f}s)")

            extract_cmd = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- bash -c "mkdir -p {remote_path} && tar -xzf {remote_tmp_tar} -C {remote_path} && rm -f {remote_tmp_tar}"'
            logger.info("📦 解压到远程路径（覆盖模式）...")
            extract_start = time.time()
            try:
                run_cmd(extract_cmd, debug=debug, desc="extract archive", timeout=1800, retries=0, check=True)
            except subprocess.CalledProcessError:
                logger.error("❌ 远端解压失败")
                return
            extract_end = time.time()
            extract_time = extract_end - extract_start
            logger.success(f"✅ 解压完成 (耗时: {extract_time:.2f}s)")

            end_time = time.time()
            total_time = end_time - start_time

            logger.info("\n" + "=" * 60)
            logger.info("⏱️  首次压缩同步耗时统计")
            logger.info("=" * 60)
            logger.info(f"  1. 压缩文件:   {compress_time:.2f}s")
            logger.info(f"  2. 上传文件:   {upload_time:.2f}s")
            logger.info(f"  3. 远端解压:   {extract_time:.2f}s")
            logger.info(f"  总耗时:        {total_time:.2f}s")
            logger.info("=" * 60)
            logger.success("🎉 首次同步完成！开始文件变更监听...")
            logger.info("=" * 60)
            return

    # 收集需要上传的文件和需要创建的目录
    directories_to_create = set()
    files_to_upload = []
    files_skipped = 0

    for root, dirs, files in os.walk(local_path):
        # 排除隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            # 跳过隐藏文件
            if file.startswith('.'):
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, local_path)

            # 检查是否应排除
            should_exclude = False
            for exclude_path in exclude_paths:
                if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(
                        exclude_path + '/'):
                    should_exclude = True
                    if debug:
                        logger.debug(f'排除文件: {rel_path} (匹配排除模式: {exclude_path})')
                    break

            if should_exclude:
                continue

            # 计算本地文件 MD5
            local_md5 = calculate_file_md5(file_path)

            # 检查是否需要上传
            need_upload = True
            if rel_path in remote_files_md5:
                remote_md5 = remote_files_md5[rel_path]
                if local_md5 == remote_md5:
                    need_upload = False
                    files_skipped += 1

            if need_upload:
                remote_dir = os.path.dirname(os.path.join(remote_path, rel_path))
                directories_to_create.add(remote_dir)
                files_to_upload.append((file_path, rel_path))

    local_total_files = files_skipped + len(files_to_upload)
    logger.info(
        f"📊 清单汇总 -> 远程: {len(remote_files_md5)} | 本地: {local_total_files} | 待上传: {len(files_to_upload)}")

    # 智能快速路径：如果待上传文件数超过100，自动切换到压缩打包上传
    if len(files_to_upload) > 100:
        logger.info("🗜️  待上传文件数超过阈值 (100)，使用压缩打包快速路径...")
        try:
            logger.info("📦 正在创建压缩包...")
            compress_start = time.time()
            with tempfile.TemporaryDirectory() as tmp_dir:
                tar_path = os.path.join(tmp_dir, 'sync_upload.tar.gz')
                compress_dir(local_path, tar_path, exclude_paths, debug)
                compress_end = time.time()
                compress_time = compress_end - compress_start

                compressed_size = os.path.getsize(tar_path)
                logger.success(f"✅ 压缩完成: {format_file_size(compressed_size)} (耗时: {compress_time:.2f}s)")

                remote_tmp_tar = "/tmp/sync_archive.tar.gz"
                upload_cmd = f'tess kubectl --cluster {cluster} -n {namespace} cp {tar_path} {pod_name}:{remote_tmp_tar}'
                logger.info("📤 上传压缩包到 Pod /tmp...")
                upload_start = time.time()
                run_cmd(upload_cmd, debug=debug, desc="upload archive", timeout=1800, retries=1, retry_delay=2.0,
                        check=True)
                upload_end = time.time()
                upload_time = upload_end - upload_start
                logger.success(f"✅ 压缩包上传成功 (耗时: {upload_time:.2f}s)")

                extract_cmd = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- bash -c "mkdir -p {remote_path} && tar -xzf {remote_tmp_tar} -C {remote_path} && rm -f {remote_tmp_tar}"'
                logger.info("📦 解压到远程路径（覆盖模式）...")
                extract_start = time.time()
                run_cmd(extract_cmd, debug=debug, desc="extract archive", timeout=1800, retries=0, check=True)
                extract_end = time.time()
                extract_time = extract_end - extract_start
                logger.success(f"✅ 解压完成 (耗时: {extract_time:.2f}s)")

            end_time = time.time()
            total_time = end_time - start_time

            logger.info("\n" + "=" * 60)
            logger.info("⏱️  快速压缩同步耗时统计")
            logger.info("=" * 60)
            logger.info(f"  1. 压缩文件:   {compress_time:.2f}s")
            logger.info(f"  2. 上传文件:   {upload_time:.2f}s")
            logger.info(f"  3. 远端解压:   {extract_time:.2f}s")
            logger.info(f"  总耗时:        {total_time:.2f}s")
            logger.info("=" * 60)
            logger.success("🎉 初始同步完成！开始文件变更监听...")
            logger.info("=" * 60)
            return
        except subprocess.CalledProcessError:
            logger.error("❌ 压缩快速路径失败，回退到增量上传")
        except Exception as e:
            logger.error(f"❌ 创建或上传压缩包失败: {e}，回退到增量上传")

    logger.info("=" * 60)
    logger.info("开始增量上传...")
    logger.info("=" * 60)

    # 批量创建目录
    if directories_to_create:
        sorted_dirs = sorted(directories_to_create)
        filtered_dirs = []

        for dir_path in sorted_dirs:
            is_redundant = False
            for other_dir in sorted_dirs:
                if other_dir != dir_path and other_dir.startswith(dir_path + '/'):
                    is_redundant = True
                    break

            if not is_redundant:
                filtered_dirs.append(dir_path)

        if filtered_dirs:
            logger.info(f"\n📁 创建远程目录: {len(filtered_dirs)} 个目录")
            all_dirs = ' '.join(filtered_dirs)
            mkdir_command = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- mkdir -p {all_dirs}'
            try:
                run_cmd(mkdir_command, debug=debug, desc="mkdir remote dirs", timeout=300, retries=1, retry_delay=1.0,
                        check=True)
                logger.success(f"✅ 目录创建成功: {len(filtered_dirs)} 个目录")
            except subprocess.CalledProcessError:
                logger.error("❌ 目录创建失败")

    # 并发上传文件
    if files_to_upload:
        logger.info(f"\n开始并发文件上传... (最大并发数: {max_workers})")

        completed_files = 0
        completed_lock = threading.Lock()
        total_files = len(files_to_upload)

        def upload_single_file(file_info):
            nonlocal completed_files
            file_path, rel_path = file_info
            file_size = os.path.getsize(file_path)
            size_str = format_file_size(file_size)
            logger.info(f"📤 上传文件: {rel_path} ({size_str})")
            command = f'tess kubectl --cluster {cluster} -n {namespace} cp {file_path} {pod_name}:{os.path.join(remote_path, rel_path)}'

            # 重试机制
            max_retries = 3
            start_one = time.time()
            for attempt in range(max_retries):
                try:
                    run_cmd(
                        command,
                        debug=debug,
                        desc=f"upload file {rel_path}",
                        timeout=1800,
                        retries=0,
                        check=True,
                    )
                    end_one = time.time()
                    sync_time = end_one - start_one

                    with completed_lock:
                        completed_files += 1
                        progress = (completed_files / total_files) * 100

                    if attempt > 0:
                        logger.success(
                            f"✅ 文件上传成功: {rel_path} (耗时: {sync_time:.2f}s) (重试 {attempt} 次后成功) [{progress:.1f}%]"
                        )
                    else:
                        logger.success(f"✅ 文件上传成功: {rel_path} (耗时: {sync_time:.2f}s) [{progress:.1f}%]")
                    return True
                except subprocess.CalledProcessError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"🔄 重试文件上传: {rel_path} (第 {attempt + 1} 次尝试)")
                        continue

                    end_one = time.time()
                    sync_time = end_one - start_one

                    with completed_lock:
                        completed_files += 1
                        progress = (completed_files / total_files) * 100

                    logger.error(
                        f"❌ 文件上传失败: {rel_path} - 错误码: {e.returncode} ({max_retries} 次重试后失败) (耗时: {sync_time:.2f}s) [{progress:.1f}%]"
                    )
                    return False

        # 使用线程池并发上传
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            logger.info(f"📊 开始并发上传，最大并发数: {max_workers}")

            future_to_file = {executor.submit(upload_single_file, file_info): file_info for file_info in
                              files_to_upload}

            successful_uploads = 0
            failed_uploads = 0

            for future in future_to_file:
                try:
                    if future.result():
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
                except Exception as e:
                    file_path = future_to_file[future][0]
                    logger.error(f"❌ 文件上传异常: {file_path} - 错误: {e}")
                    failed_uploads += 1

            logger.info(f"\n📊 上传完成统计: ✅ {successful_uploads} 成功, ❌ {failed_uploads} 失败")
    else:
        logger.info(f"\n无文件需要上传")

    end_time = time.time()
    total_time = end_time - start_time
    logger.info(f"\n⏱️  初始同步完成，总耗时: {total_time:.2f} 秒")
    logger.info("=" * 60)
    logger.success("🎉 初始同步完成！开始文件变更监听...")
    logger.info("=" * 60)


# ========== 文件监听处理器 ==========

class FileChangeHandler(FileSystemEventHandler):
    """处理文件变更事件的监听器"""

    def __init__(self, local_path, namespace, pod_name, remote_path, cluster, executor, debug=False,
                 show_concurrency=False, exclude_paths=None, debounce_seconds=1.0):
        self.local_path = local_path
        self.namespace = namespace
        self.pod_name = pod_name
        self.remote_path = remote_path
        self.cluster = cluster
        self.executor = executor
        self.debug = debug
        self.show_concurrency = show_concurrency
        self.exclude_paths = exclude_paths if exclude_paths is not None else []
        self.processing_files = {}  # 跟踪正在处理的文件
        self.debounce_timers = {}  # 跟踪每个文件的防抖定时器
        self.debounce_seconds = debounce_seconds  # 防抖延迟时间（秒）
        self.file_locks = {}  # 为每个文件创建锁，避免并发问题
        self.pending_uploads = {}  # 跟踪等待上传的文件（当文件正在上传时，标记需要再次上传）

    def get_active_tasks_count(self):
        """获取当前活跃任务数"""
        return len([f for f in self.processing_files.values() if not f.done()])

    def get_active_files(self):
        """获取正在处理的文件列表"""
        active_files = []
        for file_path, future in self.processing_files.items():
            if not future.done():
                rel_path = os.path.relpath(file_path, self.local_path)
                active_files.append(rel_path)
        return active_files

    def get_concurrency_info(self):
        """获取并发信息"""
        active_tasks = self.get_active_tasks_count()
        max_workers = self.executor._max_workers
        total_processing = len(self.processing_files)
        completed_tasks = total_processing - active_tasks

        return {
            'active': active_tasks,
            'max': max_workers,
            'available': max_workers - active_tasks,
            'total_processing': total_processing,
            'completed': completed_tasks
        }

    def print_concurrency_status(self):
        """打印并发状态"""
        concurrency_info = self.get_concurrency_info()
        active = concurrency_info['active']
        max_workers = concurrency_info['max']
        available = concurrency_info['available']

        # 根据并发水平选择不同图标
        if active == 0:
            icon = "🟢"
        elif active < max_workers * 0.5:
            icon = "🟡"
        elif active < max_workers * 0.8:
            icon = "🟠"
        else:
            icon = "🔴"

        usage_percent = (active / max_workers) * 100 if max_workers > 0 else 0

        if self.show_concurrency:
            completed = concurrency_info['completed']
            total_processing = concurrency_info['total_processing']
            logger.info(
                f"{icon} 并发状态: {active}/{max_workers} (可用: {available}, 使用率: {usage_percent:.1f}%, 总处理: {total_processing}, 已完成: {completed})")

            if active > 0:
                active_files = self.get_active_files()
                if active_files:
                    logger.info(f"   正在处理: {', '.join(active_files[:3])}{'...' if len(active_files) > 3 else ''}")
        else:
            completed = concurrency_info['completed']
            total_processing = concurrency_info['total_processing']
            logger.info(f"{icon} 并发: {active}/{max_workers} (总处理: {total_processing}, 已完成: {completed})")

    def on_modified(self, event):
        """文件修改事件"""
        # 添加调试日志
        if self.debug:
            logger.debug(f"[监听] on_modified 事件: {event.src_path}, is_directory={event.is_directory}")

        if event.is_directory:
            return

        # 排除隐藏文件
        if any(part.startswith('.') for part in event.src_path.split(os.sep)):
            return

        # 排除临时文件和备份文件
        file_name = os.path.basename(event.src_path)
        # 常见的临时文件后缀和模式
        temp_patterns = [
            file_name.endswith('~'),  # vim/emacs 备份文件
            file_name.endswith('.swp'),  # vim 交换文件
            file_name.endswith('.swo'),  # vim 交换文件
            file_name.endswith('.swn'),  # vim 交换文件
            file_name.endswith('.tmp'),  # 临时文件
            file_name.endswith('.bak'),  # 备份文件
            file_name.startswith('.#'),  # emacs 锁文件
            file_name.endswith('#'),  # emacs 自动保存文件
            file_name.startswith('~'),  # 临时文件
            '.tmp.' in file_name,  # 临时文件
            file_name.endswith('.temp'),  # 临时文件
        ]
        if any(temp_patterns):
            if self.debug:
                logger.debug(f'忽略临时文件: {file_name}')
            return

        # 检查是否应排除
        rel_path = os.path.relpath(event.src_path, self.local_path)
        for exclude_path in self.exclude_paths:
            if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(
                    exclude_path + '/'):
                if self.debug:
                    logger.debug(f'忽略修改文件: {rel_path} (匹配排除模式: {exclude_path})')
                return

        self.upload_file(event.src_path)

    def on_created(self, event):
        """文件创建事件"""
        # 添加调试日志
        if self.debug:
            logger.debug(f"[监听] on_created 事件: {event.src_path}, is_directory={event.is_directory}")

        if event.is_directory:
            return

        # 排除隐藏文件
        if any(part.startswith('.') for part in event.src_path.split(os.sep)):
            return

        # 排除临时文件和备份文件
        file_name = os.path.basename(event.src_path)
        # 常见的临时文件后缀和模式
        temp_patterns = [
            file_name.endswith('~'),  # vim/emacs 备份文件
            file_name.endswith('.swp'),  # vim 交换文件
            file_name.endswith('.swo'),  # vim 交换文件
            file_name.endswith('.swn'),  # vim 交换文件
            file_name.endswith('.tmp'),  # 临时文件
            file_name.endswith('.bak'),  # 备份文件
            file_name.startswith('.#'),  # emacs 锁文件
            file_name.endswith('#'),  # emacs 自动保存文件
            file_name.startswith('~'),  # 临时文件
            '.tmp.' in file_name,  # 临时文件
            file_name.endswith('.temp'),  # 临时文件
        ]
        if any(temp_patterns):
            if self.debug:
                logger.debug(f'忽略临时文件: {file_name}')
            return

        # 检查是否应排除
        rel_path = os.path.relpath(event.src_path, self.local_path)
        for exclude_path in self.exclude_paths:
            if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(
                    exclude_path + '/'):
                if self.debug:
                    logger.debug(f'忽略创建文件: {rel_path} (匹配排除模式: {exclude_path})')
                return

        self.upload_file(event.src_path)

    def on_moved(self, event):
        """文件移动/重命名事件（捕获 AI 工具的 atomic write 操作）"""
        if self.debug:
            logger.debug(f"[监听] on_moved 事件: src={event.src_path}, dest={event.dest_path}, is_directory={event.is_directory}")

        if event.is_directory:
            return

        # 检查目录：忽略从监听目录外移动进来的操作，或者目标是临时文件的移动
        # AI 工具通常会：tmp_file -> 最终文件（这是正常的保存操作，需要处理）
        # 或者：原文件 -> tmp_file（这是开始写，可以忽略）

        dest_path = event.dest_path
        src_path = event.src_path

        # 排除隐藏文件
        if any(part.startswith('.') for part in dest_path.split(os.sep)):
            if self.debug:
                logger.debug(f'忽略隐藏文件移动: {dest_path}')
            return

        # 检查是否应排除
        rel_path = os.path.relpath(dest_path, self.local_path)
        for exclude_path in self.exclude_paths:
            if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(
                    exclude_path + '/'):
                if self.debug:
                    logger.debug(f'忽略移动文件: {rel_path} (匹配排除模式: {exclude_path})')
                return

        # 如果源路径是临时文件模式，且目标文件不在暂存区域，这可能是 AI 的 atomic write
        # 常见的临时文件后缀
        src_name = os.path.basename(src_path)
        is_tmp_file = (
            src_name.endswith('.tmp') or
            src_name.endswith('.temp') or
            '.tmp.' in src_name or
            src_name.startswith('.')  # 隐藏的临时文件
        )

        # 目标文件如果在监听目录内，且源是临时文件，这是正常的保存
        # 如果源是正常文件，目标在临时位置，忽略
        dest_in_watch = dest_path.startswith(self.local_path)

        if dest_in_watch:
            if self.debug:
                logger.debug(f'处理文件移动（AI 保存检测）: {src_path} -> {dest_path}')
            # 触发目标文件的上传
            self.upload_file(dest_path)
        else:
            if self.debug:
                logger.debug(f'目标文件不在监听目录内，忽略: {dest_path}')

    def upload_file(self, file_path):
        """上传文件到 Pod（带防抖动）"""
        rel_path = os.path.relpath(file_path, self.local_path)

        if self.debug:
            logger.debug(f"[防抖] 收到文件变更请求: {rel_path} (完整路径: {file_path})")

        # 如果该文件已有防抖定时器在运行，取消它
        if file_path in self.debounce_timers:
            old_timer = self.debounce_timers[file_path]
            if old_timer.is_alive():
                if self.debug:
                    logger.debug(f"取消旧的防抖定时器: {rel_path}")
                old_timer.cancel()
            del self.debounce_timers[file_path]

        # 如果该文件正在上传，不要取消它，而是设置待上传标记
        if file_path in self.processing_files:
            old_future = self.processing_files[file_path]
            if not old_future.done():
                # 设置待上传标记，让上传完成后重新触发
                self.pending_uploads[file_path] = True
                if self.debug:
                    logger.debug(f"文件正在上传中，设置待上传标记: {rel_path}")
                # 不创建新的防抖定时器，让当前上传完成后自动处理
                return

        logger.info(f"🔍 检测到文件变更: {rel_path} (将在 {self.debounce_seconds}s 后上传)")

        # 创建新的防抖定时器
        timer = threading.Timer(self.debounce_seconds, self._debounced_upload, args=[file_path])
        self.debounce_timers[file_path] = timer
        timer.start()

        if self.debug:
            logger.debug(f"[防抖] 定时器已创建，将在 {self.debounce_seconds}s 后执行上传")

    def _debounced_upload(self, file_path):
        """防抖后实际执行上传"""
        rel_path = os.path.relpath(file_path, self.local_path)

        # 从防抖定时器字典中移除
        if file_path in self.debounce_timers:
            del self.debounce_timers[file_path]

        # 检查文件是否已经在上传中
        if file_path in self.processing_files:
            old_future = self.processing_files[file_path]
            if not old_future.done():
                # 文件正在上传中，标记需要在当前上传完成后再次上传
                self.pending_uploads[file_path] = True
                if self.debug:
                    logger.debug(f"文件正在上传中，标记为待上传: {rel_path}")
                return

        if self.debug:
            logger.debug(f"防抖完成，开始上传: {rel_path}")

        # 提交上传任务
        future = self.executor.submit(self._upload_file, file_path)
        self.processing_files[file_path] = future

    def _upload_file(self, file_path):
        """实际上传文件的内部方法"""
        start_time = time.time()
        try:
            rel_path = os.path.relpath(file_path, self.local_path)
            file_size = os.path.getsize(file_path)
            size_str = format_file_size(file_size)

            # 确保远程目录存在
            remote_dir = os.path.dirname(os.path.join(self.remote_path, rel_path))
            mkdir_command = f'tess kubectl --cluster {self.cluster} -n {self.namespace} exec {self.pod_name} -- mkdir -p {remote_dir}'
            try:
                run_cmd(mkdir_command, debug=self.debug, desc=f"mkdir {remote_dir}", timeout=120, retries=1,
                        retry_delay=1.0, check=True)
            except subprocess.CalledProcessError:
                # mkdir 失败不直接阻断，仍继续尝试上传（有些情况下目录已存在但返回码异常）
                logger.error(f"❌ 创建远程目录失败: {remote_dir}")

            # 上传文件
            command = f'tess kubectl --cluster {self.cluster} -n {self.namespace} cp {file_path} {self.pod_name}:{os.path.join(self.remote_path, rel_path)}'

            # 重试机制（交给 run_cmd 执行）
            max_retries = 3
            try:
                run_cmd(command, debug=self.debug, desc=f"realtime upload {rel_path}", timeout=1800,
                        retries=max_retries - 1, retry_delay=1.0, check=True)
                end_time = time.time()
                sync_time = end_time - start_time
                logger.success(f"✅ 文件同步成功: {rel_path} (耗时: {sync_time:.2f}s) [实时同步]")
                return
            except subprocess.CalledProcessError as e:
                end_time = time.time()
                sync_time = end_time - start_time
                logger.error(
                    f"❌ 文件同步失败: {rel_path} - 错误码: {e.returncode} ({max_retries} 次重试后失败) (耗时: {sync_time:.2f}s)")
        finally:
            # 无论成功还是失败，都从处理列表中移除
            if file_path in self.processing_files:
                del self.processing_files[file_path]

            # 检查是否有待上传的标记
            if file_path in self.pending_uploads:
                del self.pending_uploads[file_path]
                rel_path = os.path.relpath(file_path, self.local_path)
                if self.debug:
                    logger.debug(f"检测到待上传标记，重新启动防抖: {rel_path}")
                # 不立即上传，而是重新触发防抖，避免文件还在编辑中
                # 这样可以合并上传期间的多次修改
                timer = threading.Timer(self.debounce_seconds, self._debounced_upload, args=[file_path])
                self.debounce_timers[file_path] = timer
                timer.start()
                logger.info(f"🔄 检测到新变更，将在 {self.debounce_seconds}s 后重新上传: {rel_path}")


# ========== 初始化配置 ==========

def init_config(project_name, local_path):
    """初始化配置文件"""
    config_path = get_config_path(project_name)

    # 检查配置文件是否已存在
    if config_path.exists():
        # 检查是否缺少 local_path 字段，如果缺少则补充
        config = load_config(project_name)
        if 'local_path' not in config or not config.get('local_path'):
            config['local_path'] = local_path
            save_config(project_name, config)
            logger.info("=" * 60)
            logger.success("✅ 配置文件已更新（添加 local_path）")
            logger.info("=" * 60)
            logger.info(f"📁 配置文件位置: {config_path}")
            logger.info(f"📝 local_path: {local_path}")
            logger.info("=" * 60)
            logger.info("\n✨ 使用以下命令开始同步：")
            logger.info(f"   python3 {sys.argv[0]} --project {project_name}")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("⚠️  配置文件已存在")
            logger.info("=" * 60)
            logger.info(f"📁 配置文件位置: {config_path}")
            logger.info("=" * 60)
            logger.info("\n📝 请直接编辑配置文件：")
            logger.info(f"   vim {config_path}")
            logger.info("\n✨ 编辑完成后，使用以下命令开始同步：")
            logger.info(f"   python3 {sys.argv[0]} --project {project_name}")
            logger.info("=" * 60)
        return

    # 创建示例配置
    example_config = {
        "cluster": "908",
        "namespace": "sdsnushare01-dev",
        "pod_label": "app=your-app",
        "remote_path": "/mnt/gfs-develop/workspace",
        "local_path": local_path,
        "compress_threshold": 50,
        "max_workers": 10,
        "debug": False,
        "show_concurrency": False,
        "no_watch": False,
        "skip_verify": False,
        "debounce_seconds": 1.0,
        "exclude_paths": [
            "node_modules",
            "*.log",
            "dist/build"
        ]
    }

    # 保存配置
    save_config(project_name, example_config)

    logger.info("=" * 60)
    logger.success("✅ 配置文件已创建")
    logger.info("=" * 60)
    logger.info(f"📁 配置文件位置: {config_path}")
    logger.info("=" * 60)
    logger.info("📋 当前配置内容（示例）:")
    logger.info("=" * 60)
    logger.info(json.dumps(example_config, indent=4, ensure_ascii=False))
    logger.info("=" * 60)
    logger.info("\n📝 请编辑配置文件，填入正确的参数值：")
    logger.info(f"   vim {config_path}")
    logger.info("\n✨ 编辑完成后，使用以下命令开始同步：")
    logger.info(f"   python3 {sys.argv[0]} --project {project_name}")
    logger.info("=" * 60)


# ========== 列出所有项目 ==========

def list_projects():
    """列出所有已配置的项目"""
    home = Path.home()
    sync2pod_dir = home / '.sync2pod'

    if not sync2pod_dir.exists():
        logger.info("=" * 60)
        logger.info("📋 没有找到任何项目配置")
        logger.info("=" * 60)
        logger.info("\n请先初始化项目配置：")
        logger.info("  python3 sync_local_to_pod_optimized.py --init-config --local-path <本地路径>")
        logger.info("=" * 60)
        return

    # 收集所有项目
    projects = []
    for project_dir in sync2pod_dir.iterdir():
        if project_dir.is_dir():
            config_file = project_dir / 'sync_config.json'
            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    projects.append({
                        'name': project_dir.name,
                        'local_path': config.get('local_path', 'N/A'),
                        'remote_path': config.get('remote_path', 'N/A'),
                        'cluster': config.get('cluster', 'N/A'),
                        'namespace': config.get('namespace', 'N/A')
                    })
                except:
                    pass

    if not projects:
        logger.info("=" * 60)
        logger.info("📋 没有找到任何有效的项目配置")
        logger.info("=" * 60)
        return

    logger.info("=" * 60)
    logger.info(f"📋 已配置的项目 (共 {len(projects)} 个)")
    logger.info("=" * 60)
    for i, proj in enumerate(projects, 1):
        logger.info(f"\n{i}. 项目名: {proj['name']}")
        logger.info(f"   本地路径: {proj['local_path']}")
        logger.info(f"   远程路径: {proj['remote_path']}")
        logger.info(f"   集群: {proj['cluster']}")
        logger.info(f"   命名空间: {proj['namespace']}")
    logger.info("\n" + "=" * 60)
    logger.info("💡 使用以下命令开始同步：")
    logger.info(f"   python3 {sys.argv[0]} --project <项目名>")
    logger.info("=" * 60)


# ========== 主流程 ==========

def main():
    parser = argparse.ArgumentParser(
        description='优化版本地目录同步到K8s Pod工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:

  1. 初始化配置:
     python3 sync_local_to_pod_optimized.py --init-config --local-path /Users/xchen17/workspace/heketi

  2. 查看所有项目:
     python3 sync_local_to_pod_optimized.py --list-projects

  3. 开始同步:
     python3 sync_local_to_pod_optimized.py --project heketi

  4. 强制全量同步:
     python3 sync_local_to_pod_optimized.py --project heketi --force
        """
    )

    # 模式选择参数
    parser.add_argument('--init-config', action='store_true', help='初始化配置文件（需配合 --local-path）')
    parser.add_argument('--list-projects', action='store_true', help='列出所有已配置的项目')
    parser.add_argument('--project', help='项目名称（用于同步）')

    # 初始化所需参数
    parser.add_argument('--local-path', help='本地目录路径（仅用于初始化）')

    # 同步参数
    parser.add_argument('--force', action='store_true', help='强制全量同步（仅命令行使用，不保存到配置文件）')
    parser.add_argument('--skip-verify', action='store_true',
                        help='跳过同步前的配置确认（可在配置文件中设置，默认为 false）')

    args = parser.parse_args()

    # 模式1：列出所有项目
    if args.list_projects:
        list_projects()
        return

    # 模式2：初始化配置
    if args.init_config:
        if not args.local_path:
            logger.error("❌ 错误: --init-config 需要配合 --local-path 使用")
            sys.exit(1)

        local_path = os.path.abspath(args.local_path)
        if not os.path.exists(local_path):
            logger.error(f"❌ 错误: 本地路径不存在: {local_path}")
            sys.exit(1)

        # 从本地路径推导项目名
        project_name = os.path.basename(os.path.normpath(local_path))
        init_config(project_name, local_path)
        return

    # 模式3：同步 - 仅支持 --project
    if not args.project:
        logger.error("❌ 错误: 请指定操作模式")
        logger.info("\n使用说明:")
        logger.info("  初始化:   python3 sync_local_to_pod_optimized.py --init-config --local-path <本地路径>")
        logger.info("  查看项目: python3 sync_local_to_pod_optimized.py --list-projects")
        logger.info("  同步:     python3 sync_local_to_pod_optimized.py --project <项目名>")
        sys.exit(1)

    project_name = args.project

    # 检查项目名是否为路径（常见错误）
    if os.path.isabs(project_name) or '/' in project_name:
        logger.error(f"❌ 错误: --project 应传入项目名称，而非路径")
        logger.info(f"\n示例: --project patching-verify-contoller (而非完整路径)")
        logger.info(f"  当前传入: {project_name}")
        sys.exit(1)

    # 获取所有已配置的项目
    home = Path.home()
    sync2pod_dir = home / '.sync2pod'
    existing_projects = []
    if sync2pod_dir.exists():
        for project_dir in sync2pod_dir.iterdir():
            if project_dir.is_dir():
                config_file = project_dir / 'sync_config.json'
                if config_file.exists():
                    existing_projects.append(project_dir.name)

    # 验证项目是否存在
    if project_name not in existing_projects:
        logger.error(f"❌ 错误: 项目 '{project_name}' 不存在")
        if existing_projects:
            logger.info(f"\n已配置的项目 ({len(existing_projects)} 个)：")
            for proj in existing_projects:
                logger.info(f"  - {proj}")
        else:
            logger.info(f"\n没有任何已配置的项目，请先初始化：")
            logger.info(f"  初始化: python3 {sys.argv[0]} --init-config --local-path <本地路径>")
        logger.info(f"\n使用以下命令查看项目：")
        logger.info(f"  python3 {sys.argv[0]} --list-projects")
        sys.exit(1)

    # 加载配置文件
    config_path = get_config_path(project_name)
    config = load_config(project_name)

    config = load_config(project_name)

    # force 参数仅从命令行读取，不持久化
    # skip_verify 可从命令行或配置文件读取，命令行优先
    force_full_sync = args.force
    skip_verify = args.skip_verify if args.skip_verify else config.get('skip_verify', False)

    # 验证必需参数
    required_fields = ['cluster', 'namespace', 'pod_label', 'remote_path', 'local_path']
    missing_fields = [field for field in required_fields if not config.get(field)]

    if missing_fields:
        logger.error(f"❌ 错误: 配置文件缺少必需字段: {', '.join(missing_fields)}")
        logger.info(f"\n请编辑配置文件: {config_path}")
        sys.exit(1)

    # 获取参数
    cluster = config['cluster']
    namespace = config['namespace']
    pod_label = config['pod_label']
    remote_path = config['remote_path']
    local_path = config['local_path']
    exclude_paths = config.get('exclude_paths', [])
    debug = config.get('debug', False)
    max_workers = config.get('max_workers', 10)
    show_concurrency = config.get('show_concurrency', False)
    no_watch = config.get('no_watch', False)
    debounce_seconds = config.get('debounce_seconds', 1.0)  # 默认1秒防抖

    # 如果需要验证，显示重要配置信息并等待确认
    if not skip_verify:
        logger.info("=" * 60)
        logger.info("⚠️  同步前配置确认")
        logger.info("=" * 60)
        logger.info(f"配置文件 (config):   {config_path}")
        logger.info(f"集群 (cluster):     {cluster}")
        logger.info(f"命名空间 (namespace): {namespace}")
        logger.info(f"Pod标签 (pod_label): {pod_label}")
        logger.info(f"远程路径 (remote_path): {remote_path}")
        logger.info(f"本地路径 (local_path):  {local_path}")
        logger.info("=" * 60)
        logger.info("⚠️  请仔细核对以上配置，确认无误后按回车继续...")
        logger.info("   (如需跳过此确认，可在配置文件中设置 skip_verify: true")
        logger.info("    或使用命令行参数 --skip-verify)")
        logger.info("=" * 60)
        try:
            input()
        except KeyboardInterrupt:
            logger.error("\n\n❌ 用户取消同步")
            sys.exit(0)
        logger.success("✅ 确认完成，开始同步...\n")

    # 验证本地路径
    if not os.path.exists(local_path):
        logger.error(f"❌ 错误: 本地路径不存在: {local_path}")
        logger.info(f"\n请检查配置文件中的 local_path: {config_path}")
        sys.exit(1)

    if not (cluster and namespace and pod_label and remote_path):
        logger.error('cluster/namespace/pod_label/remote_path 必填')
        sys.exit(1)

    # 配置logger（根据debug模式）
    configure_logger(debug)

    # 选择 pod
    pod_name = None
    try:
        pod_name = select_running_pod_by_label(cluster, namespace, pod_label, debug=debug)
    except Exception as e:
        logger.error(f"❌ 选择 Pod 失败: {e}")
        sys.exit(1)
    logger.info(f"🎯 目标 Pod: {pod_name} (namespace={namespace}, label={pod_label})")
    if debug:
        logger.debug(f'选择到 pod: {pod_name}')

    # 判断同步方式
    if force_full_sync:
        # 强制全量同步：直接压缩上传，不做 MD5 对比
        force_sync_start = time.time()

        file_count = count_files(local_path, exclude_paths)
        if debug:
            logger.debug(f'本地文件数: {file_count}')
        logger.info(f'🗜️  强制全量同步模式，使用压缩打包上传...')

        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = os.path.join(tmp_dir, 'sync_upload.tar.gz')

            # 1. 压缩文件
            logger.info('📦 正在压缩本地目录...')
            compress_start = time.time()
            compress_dir(local_path, tar_path, exclude_paths, debug)
            compress_end = time.time()
            compress_time = compress_end - compress_start

            compressed_size = os.path.getsize(tar_path)
            logger.success(f'✅ 压缩完成: {format_file_size(compressed_size)} (耗时: {compress_time:.2f}s)')

            # 计算 remote_path 的父目录
            remote_parent = os.path.dirname(remote_path)
            remote_tar_path = os.path.join(remote_parent, 'sync_upload.tar.gz')

            # 优化：合并多个 kubectl exec 命令减少 IO
            cmd_cp = f'tess kubectl --cluster {cluster} -n {namespace} cp {tar_path} {pod_name}:{remote_tar_path}'
            # 合并清空、解压、删除为一次 kubectl exec 调用
            cmd_extract = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- bash -c "rm -rf {remote_path}/* && tar -xzf {remote_tar_path} -C {remote_path} && rm {remote_tar_path}"'

            if debug:
                logger.debug(f'上传压缩包命令: {cmd_cp}')
                logger.debug(f'解压并清理命令: {cmd_extract}')

            # 2. 上传压缩包
            logger.info('📤 上传压缩包...')
            upload_start = time.time()
            try:
                run_cmd(cmd_cp, debug=debug, desc="force upload archive", timeout=1800, retries=1, retry_delay=2.0,
                        check=True)
            except subprocess.CalledProcessError:
                logger.error("❌ 上传压缩包失败")
                sys.exit(1)
            upload_end = time.time()
            upload_time = upload_end - upload_start
            logger.success(f'✅ 上传完成 (耗时: {upload_time:.2f}s)')

            # 3. 远端解压
            logger.info('📦 解压并清理 (清空 -> 解压 -> 删除临时文件)...')
            extract_start = time.time()
            try:
                run_cmd(cmd_extract, debug=debug, desc="force extract archive", timeout=1800, retries=0, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"❌ 解压并清理失败 (错误码: {e.returncode})")
                sys.exit(1)
            extract_end = time.time()
            extract_time = extract_end - extract_start
            logger.success(f'✅ 解压完成 (耗时: {extract_time:.2f}s)')

        force_sync_end = time.time()
        total_time = force_sync_end - force_sync_start

        logger.info("\n" + "=" * 60)
        logger.info("⏱️  强制全量同步耗时统计")
        logger.info("=" * 60)
        logger.info(f"  1. 压缩文件:   {compress_time:.2f}s")
        logger.info(f"  2. 上传文件:   {upload_time:.2f}s")
        logger.info(f"  3. 远端解压:   {extract_time:.2f}s")
        logger.info(f"  总耗时:        {total_time:.2f}s")
        logger.info("=" * 60)
    else:
        # 智能增量同步：总是进行 MD5 对比，根据待上传文件数选择上传方式
        file_count = count_files(local_path, exclude_paths)
        if debug:
            logger.debug(f'本地文件数: {file_count}')
        logger.info(f'📊 本地文件数: {file_count}，开始 MD5 对比增量同步...')
        upload_initial_files(local_path, namespace, pod_name, remote_path, cluster, debug, max_workers, exclude_paths)

    # 启动文件监听（除非配置文件中指定 no_watch）
    if not no_watch:
        logger.info(f"👀 启动文件变更监听... (最大并发数: {max_workers}, 防抖延迟: {debounce_seconds}s)")
        logger.info(f"📂 监听路径: {local_path}")
        logger.debug(f"[监听] 检查本地路径是否存在: {os.path.exists(local_path)}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            event_handler = FileChangeHandler(
                local_path, namespace, pod_name, remote_path, cluster,
                executor, debug, show_concurrency, exclude_paths, debounce_seconds
            )
            observer = Observer()

            # 检查 observer 是否可用
            logger.debug(f"[监听] Observer 已创建，开始调度...")
            observer.schedule(event_handler, path=local_path, recursive=True)
            logger.debug(f"[监听] 已调度监听器到路径: {local_path}, recursive=True")

            observer.start()
            logger.success(f"✅ 文件监听已启动，正在监听 {local_path} 及其子目录...")
            logger.info("=" * 60)
            logger.info("💡 提示：现在可以编辑本地文件，变更将自动同步到 Pod")
            logger.info("   按 Ctrl+C 停止监听")
            logger.info("=" * 60)

            try:
                while True:
                    # 每 30 秒显示并发状态（仅当启用详细并发信息时）
                    time.sleep(30)
                    if show_concurrency:
                        concurrency_info = event_handler.get_concurrency_info()
                        if concurrency_info['active'] > 0:
                            event_handler.print_concurrency_status()
            except KeyboardInterrupt:
                logger.info("\n⏹️  停止文件监听...")
                observer.stop()
            observer.join()
    else:
        logger.success("✅ 同步完成（文件监听已禁用）")


if __name__ == '__main__':
    # 先配置基本的logger（初始化和列表项目模式）
    configure_logger(debug=False)
    main()
