#!/usr/bin/env python3
"""sync_local_to_pod v2 unified - local directory sync to a K8s pod
with remote delete, empty-dir sync, safer path-state reconciliation,
directory move recursive resync, atomic full-sync switch, startup prune,
file-stability checks, dynamic shard splitting, remote delete guards,
dry-run planning, and remote capability checks.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from utils.shell import run_local_cmd, cmd_repr
from utils.log import setup_logging

DEFAULT_COMPRESS_THRESHOLD = 100
DEFAULT_UPLOAD_CHUNK_COUNT = 6
DEFAULT_TARGET_CHUNK_SIZE_MB = 64
MIN_UPLOAD_CHUNKS = 1
MAX_UPLOAD_CHUNKS = 16
FILE_STABLE_CHECK_INTERVAL = 0.4
FILE_STABLE_MAX_WAIT = 8.0


@dataclass
class SyncConfig:
    cluster: str
    namespace: str
    pod_label: str
    remote_parent_path: str
    local_path: str
    remote_path: str = field(init=False)
    compress_threshold: int = 100
    max_workers: int = 10
    debug: bool = False
    show_concurrency: bool = False
    no_watch: bool = False
    skip_verify: bool = False
    debounce_seconds: float = 1.0
    exclude_paths: list[str] = field(default_factory=list)
    prune: bool = True
    upload_chunk_count: int = DEFAULT_UPLOAD_CHUNK_COUNT
    target_chunk_size_mb: int = DEFAULT_TARGET_CHUNK_SIZE_MB

    def __post_init__(self) -> None:
        self.remote_path = os.path.join(
            self.remote_parent_path, os.path.basename(os.path.normpath(self.local_path))
        )
        self.upload_chunk_count = max(MIN_UPLOAD_CHUNKS, min(MAX_UPLOAD_CHUNKS, int(self.upload_chunk_count)))
        self.target_chunk_size_mb = max(1, int(self.target_chunk_size_mb))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SyncConfig":
        required = ["cluster", "namespace", "pod_label", "remote_parent_path", "local_path"]
        missing = [f for f in required if not d.get(f)]
        if missing:
            raise ValueError(f"missing required config fields: {', '.join(missing)}")
        return cls(
            cluster=d["cluster"],
            namespace=d["namespace"],
            pod_label=d["pod_label"],
            remote_parent_path=d["remote_parent_path"],
            local_path=d["local_path"],
            compress_threshold=d.get("compress_threshold", DEFAULT_COMPRESS_THRESHOLD),
            max_workers=d.get("max_workers", 10),
            debug=d.get("debug", False),
            show_concurrency=d.get("show_concurrency", False),
            no_watch=d.get("no_watch", False),
            skip_verify=d.get("skip_verify", False),
            debounce_seconds=d.get("debounce_seconds", 1.0),
            exclude_paths=d.get("exclude_paths", []),
            prune=d.get("prune", True),
            upload_chunk_count=d.get("upload_chunk_count", DEFAULT_UPLOAD_CHUNK_COUNT),
            target_chunk_size_mb=d.get("target_chunk_size_mb", DEFAULT_TARGET_CHUNK_SIZE_MB),
        )


@dataclass(frozen=True)
class UploadItem:
    local_path: str
    remote_path: str
    display_name: str


@dataclass
class SyncPlan:
    mode: str
    local_file_count: int
    local_empty_dir_count: int
    remote_file_count: int
    remote_dir_count: int
    files_to_upload_count: int
    dirs_to_create_count: int
    prune_file_count: int
    prune_dir_count: int
    would_use_archive: bool





def kubectl_base(cfg: SyncConfig) -> list[str]:
    return ["tess", "kubectl", "--cluster", cfg.cluster, "-n", cfg.namespace]


def exec_cmd(cfg: SyncConfig, pod_name: str, script: str) -> list[str]:
    return kubectl_base(cfg) + ["exec", pod_name, "--", "bash", "-lc", script]


def cp_cmd(cfg: SyncConfig, src: str, pod_name: str, dest: str) -> list[str]:
    return kubectl_base(cfg) + ["cp", src, f"{pod_name}:{dest}"]


def select_running_pod_by_label(cfg: SyncConfig) -> str:
    cmd = kubectl_base(cfg) + [
        "get",
        "pods",
        "-l",
        cfg.pod_label,
        "--field-selector=status.phase=Running",
        "-o",
        'jsonpath={.items[0].metadata.name}',
    ]
    result = run_local_cmd(cmd, debug=cfg.debug, desc="select running pod", timeout=30, retries=2)
    pod_name = (result.stdout or "").strip().strip("'\"")
    if not pod_name:
        raise RuntimeError(f"no running pod found (namespace={cfg.namespace}, label={cfg.pod_label})")
    return pod_name


def check_remote_capabilities(cfg: SyncConfig, pod_name: str) -> None:
    required = ["bash", "find", "tar", "md5sum"]
    script = "missing=(); for c in " + " ".join(required) + "; do command -v $c >/dev/null 2>&1 || missing+=($c); done; printf '%s\n' \"${missing[@]}\""
    result = run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc="check remote capabilities", timeout=60, check=False)
    missing = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if missing:
        raise RuntimeError(f"remote pod is missing required commands: {', '.join(missing)}")
    logger.success("remote capability check passed")


def is_hidden(name: str) -> bool:
    return name.startswith(".")


def is_excluded(rel_path: str, exclude_paths: list[str]) -> bool:
    rel_path = rel_path.replace(os.sep, "/")
    base = os.path.basename(rel_path)
    for pattern in exclude_paths:
        p = pattern.replace(os.sep, "/")
        if rel_path == p or rel_path.startswith(p.rstrip("/") + "/"):
            return True
        if fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(base, p):
            return True
    return False


def calculate_file_md5(file_path: str) -> str | None:
    h = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.error(f"md5 failed for {file_path}: {e}")
        return None


def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    return f"{round(size_bytes / math.pow(1024, i), 2)} {names[i]}"


def count_files(local_path: str, exclude_paths: list[str]) -> int:
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


def _dir_has_syncable_files(root: str, files: list[str], local_path: str, exclude_paths: list[str]) -> bool:
    for name in files:
        if is_hidden(name):
            continue
        rel = os.path.relpath(os.path.join(root, name), local_path)
        if not is_excluded(rel, exclude_paths):
            return True
    return False


def collect_empty_dirs(local_path: str, exclude_paths: list[str]) -> list[str]:
    empty_dirs: list[str] = []
    for root, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if not is_hidden(d)]
        dirs[:] = [
            d for d in dirs
            if not is_excluded(os.path.relpath(os.path.join(root, d), local_path), exclude_paths)
        ]
        rel_root = os.path.relpath(root, local_path)
        if rel_root == ".":
            continue
        if is_excluded(rel_root, exclude_paths):
            continue
        if not dirs and not _dir_has_syncable_files(root, files, local_path, exclude_paths):
            empty_dirs.append(rel_root)
    return empty_dirs


def collect_local_manifest(local_path: str, exclude_paths: list[str]) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    dirs: set[str] = set()
    for root, dirnames, filenames in os.walk(local_path):
        dirnames[:] = [d for d in dirnames if not is_hidden(d)]
        dirnames[:] = [
            d for d in dirnames
            if not is_excluded(os.path.relpath(os.path.join(root, d), local_path), exclude_paths)
        ]
        rel_root = os.path.relpath(root, local_path)
        if rel_root != "." and not is_excluded(rel_root, exclude_paths):
            dirs.add(rel_root)

        for name in filenames:
            if is_hidden(name):
                continue
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, local_path)
            if is_excluded(rel, exclude_paths):
                continue
            files.add(rel)
            parent = os.path.dirname(rel)
            while parent and parent != ".":
                dirs.add(parent)
                parent = os.path.dirname(parent)
    return files, dirs


def collect_syncable_files_under(base_dir: str, local_root: str, exclude_paths: list[str]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if not os.path.exists(base_dir):
        return items
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not is_hidden(d)]
        dirs[:] = [
            d for d in dirs
            if not is_excluded(os.path.relpath(os.path.join(root, d), local_root), exclude_paths)
        ]
        for name in files:
            if is_hidden(name):
                continue
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, local_root)
            if is_excluded(rel, exclude_paths):
                continue
            items.append((fp, rel))
    return items


def compress_dir(src_dir: str, out_file: str, exclude_paths: list[str], debug: bool) -> None:
    files_to_compress: list[tuple[str, str, int]] = []
    empty_dirs = collect_empty_dirs(src_dir, exclude_paths)
    logger.info("scanning files to compress...")

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
                    logger.debug(f"excluded: {rel}")
                continue
            try:
                files_to_compress.append((fp, rel, os.path.getsize(fp)))
            except OSError:
                continue

    if files_to_compress:
        logger.info("=" * 60)
        logger.info("top 10 largest files:")
        logger.info("=" * 60)
        for idx, (_, rel, sz) in enumerate(sorted(files_to_compress, key=lambda x: x[2], reverse=True)[:10], 1):
            logger.info(f"{idx:2d}. {format_file_size(sz):>10s}  {rel}")
        logger.info("=" * 60)

    if empty_dirs:
        logger.info(f"including {len(empty_dirs)} empty directories in archive")

    logger.info("compressing archive...")
    with tarfile.open(out_file, "w:gz") as tar:
        for fp, rel, _ in files_to_compress:
            tar.add(fp, arcname=rel)
        for rel in empty_dirs:
            dir_path = os.path.join(src_dir, rel)
            tar.add(dir_path, arcname=rel, recursive=False)
    logger.success(f"archive ready: {len(files_to_compress)} files, {len(empty_dirs)} empty dirs")


def is_remote_empty(cfg: SyncConfig, pod_name: str) -> bool:
    script = (
        f'if [ -d {shlex.quote(cfg.remote_path)} ]; then '
        f'find {shlex.quote(cfg.remote_path)} -mindepth 1 \\( -type f -o -type d \\) -print -quit 2>/dev/null; '
        f'fi'
    )
    result = run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc="probe remote empty", timeout=60, check=False)
    return not bool((result.stdout or "").strip())


def get_remote_files_md5(cfg: SyncConfig, pod_name: str) -> dict[str, str]:
    script = f'find {shlex.quote(cfg.remote_path)} -type f -exec md5sum {{}} \\; 2>/dev/null || true'
    result = run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc="collect remote md5", timeout=600, check=False)

    remote_files: dict[str, str] = {}
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


def get_remote_manifest(cfg: SyncConfig, pod_name: str) -> tuple[set[str], set[str]]:
    script = (
        f'if [ -d {shlex.quote(cfg.remote_path)} ]; then '
        f'find {shlex.quote(cfg.remote_path)} -mindepth 1 \\( -type f -o -type d \\) -printf "%y\\t%P\\n" 2>/dev/null; '
        f'fi'
    )
    result = run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc="collect remote manifest", timeout=600, check=False)
    files: set[str] = set()
    dirs: set[str] = set()
    for line in (result.stdout or "").splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        kind, rel = parts
        rel = rel.strip()
        if not rel or is_excluded(rel, cfg.exclude_paths):
            continue
        if kind == "f":
            files.add(rel)
        elif kind == "d":
            dirs.add(rel)
    return files, dirs


def cleanup_remote_shards(cfg: SyncConfig, pod_name: str, remote_parts: list[str]) -> None:
    if not remote_parts:
        return
    script = "rm -f " + " ".join(shlex.quote(p) for p in remote_parts)
    try:
        run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc="cleanup remote shards", timeout=60, check=False)
    except Exception:
        pass


def cleanup_local_files(paths: list[str], debug: bool = False) -> None:
    removed = 0
    for path in paths:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                removed += 1
        except OSError:
            pass
    if removed and debug:
        logger.debug(f"removed local temp files: {removed}")


def _choose_chunk_count(cfg: SyncConfig, tar_size: int) -> int:
    target_chunk_bytes = cfg.target_chunk_size_mb * 1024 * 1024
    dynamic = max(1, math.ceil(tar_size / target_chunk_bytes))
    return max(MIN_UPLOAD_CHUNKS, min(MAX_UPLOAD_CHUNKS, min(cfg.upload_chunk_count, dynamic) if tar_size <= cfg.upload_chunk_count * target_chunk_bytes else max(cfg.upload_chunk_count, dynamic)))


def _split_archive(tar_path: str, tmp_dir: str, project_name: str, cfg: SyncConfig) -> tuple[list[str], dict[int, str]]:
    tar_size = os.path.getsize(tar_path)
    chunk_count = _choose_chunk_count(cfg, tar_size)
    chunk_size = max(1, math.ceil(tar_size / chunk_count))
    chunk_files: list[str] = []
    chunk_hashes: dict[int, str] = {}

    with open(tar_path, "rb") as f:
        idx = 0
        while True:
            chunk_data = f.read(chunk_size)
            if not chunk_data:
                break
            chunk_path = os.path.join(tmp_dir, f"{project_name}_sync_part_{idx:03d}.tar.gz")
            with open(chunk_path, "wb") as cf:
                cf.write(chunk_data)
            chunk_files.append(chunk_path)
            chunk_hashes[idx] = hashlib.md5(chunk_data).hexdigest()
            idx += 1

    return chunk_files, chunk_hashes


def _upload_items_parallel(
    cfg: SyncConfig,
    pod_name: str,
    items: list[UploadItem],
    *,
    desc_prefix: str,
    timeout: int,
    retries: int,
) -> tuple[int, int, float]:
    total = len(items)
    if total == 0:
        return 0, 0, 0.0

    completed = 0
    lock = threading.Lock()

    def upload_one(item: UploadItem) -> bool:
        nonlocal completed
        t0 = time.time()
        try:
            size = format_file_size(os.path.getsize(item.local_path))
        except OSError:
            size = "unknown"

        cmd = cp_cmd(cfg, item.local_path, pod_name, item.remote_path)
        try:
            run_local_cmd(
                cmd,
                debug=cfg.debug,
                desc=f"{desc_prefix} {item.display_name}",
                timeout=timeout,
                retries=retries,
                retry_delay=1.0,
            )
            elapsed = time.time() - t0
            with lock:
                completed += 1
                pct = completed / total * 100
                logger.success(f"{item.display_name} ({size}, {elapsed:.2f}s) [{pct:.1f}%]")
            return True
        except subprocess.CalledProcessError:
            with lock:
                completed += 1
                pct = completed / total * 100
                logger.error(f"upload failed: {item.display_name} [{pct:.1f}%]")
            return False

    upload_t0 = time.time()
    with ThreadPoolExecutor(max_workers=min(cfg.max_workers, total)) as ex:
        futures = [ex.submit(upload_one, item) for item in items]
        ok = sum(1 for fut in futures if fut.result())
    elapsed = time.time() - upload_t0
    fail = total - ok
    return ok, fail, elapsed


def _upload_single_item(
    cfg: SyncConfig,
    pod_name: str,
    item: UploadItem,
    *,
    desc_prefix: str,
    timeout: int,
    retries: int,
) -> bool:
    ok, fail, _ = _upload_items_parallel(
        cfg,
        pod_name,
        [item],
        desc_prefix=desc_prefix,
        timeout=timeout,
        retries=retries,
    )
    return ok == 1 and fail == 0


def _mkdir_remote_dirs(cfg: SyncConfig, pod_name: str, remote_dirs: list[str], *, desc: str) -> bool:
    if not remote_dirs:
        return True
    deduped = sorted(set(remote_dirs))
    script = "mkdir -p " + " ".join(shlex.quote(d) for d in deduped)
    try:
        run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc=desc, timeout=300, retries=1)
        logger.success(f"remote dirs ensured: {len(deduped)}")
        return True
    except subprocess.CalledProcessError:
        logger.error("failed to ensure remote dirs")
        return False


def _is_safe_remote_target(cfg: SyncConfig, remote_path: str) -> bool:
    target = os.path.normpath(remote_path)
    remote_root = os.path.normpath(cfg.remote_path)
    parent_root = os.path.normpath(cfg.remote_parent_path)

    if target in {"", ".", "/"}:
        return False
    if target == parent_root:
        return False
    if target == remote_root:
        return True
    return target.startswith(remote_root + os.sep)


def _delete_remote_path(
    cfg: SyncConfig,
    pod_name: str,
    remote_path: str,
    *,
    is_dir: bool,
    display_name: str,
) -> bool:
    if not _is_safe_remote_target(cfg, remote_path):
        logger.error(f"unsafe remote delete blocked: {display_name} -> {remote_path}")
        return False

    quoted = shlex.quote(remote_path)
    script = f"rm -rf {quoted}" if is_dir else f"rm -f {quoted}"
    desc = f"delete remote {'dir' if is_dir else 'file'} {display_name}"
    try:
        run_local_cmd(exec_cmd(cfg, pod_name, script), debug=cfg.debug, desc=desc, timeout=120, retries=2)
        logger.success(f"remote deleted: {display_name}")
        return True
    except subprocess.CalledProcessError:
        logger.error(f"remote delete failed: {display_name}")
        return False


def _wait_for_file_stable(file_path: str, *, max_wait: float = FILE_STABLE_MAX_WAIT, interval: float = FILE_STABLE_CHECK_INTERVAL) -> bool:
    deadline = time.time() + max_wait
    last_sig: tuple[int, int] | None = None
    stable_hits = 0

    while time.time() < deadline:
        try:
            st = os.stat(file_path)
        except FileNotFoundError:
            return False
        sig = (st.st_size, st.st_mtime_ns)
        if sig == last_sig:
            stable_hits += 1
            if stable_hits >= 2:
                return True
        else:
            stable_hits = 0
            last_sig = sig
        time.sleep(interval)

    return False


def _plan_sync(cfg: SyncConfig, pod_name: str, force_full_sync: bool) -> SyncPlan:
    local_file_count = count_files(cfg.local_path, cfg.exclude_paths)
    local_empty_dirs = collect_empty_dirs(cfg.local_path, cfg.exclude_paths)
    local_empty_dir_count = len(local_empty_dirs)

    if force_full_sync:
        remote_files, remote_dirs = get_remote_manifest(cfg, pod_name)
        return SyncPlan(
            mode="forced-full",
            local_file_count=local_file_count,
            local_empty_dir_count=local_empty_dir_count,
            remote_file_count=len(remote_files),
            remote_dir_count=len(remote_dirs),
            files_to_upload_count=local_file_count,
            dirs_to_create_count=local_empty_dir_count,
            prune_file_count=len(remote_files),
            prune_dir_count=len(remote_dirs),
            would_use_archive=True,
        )

    remote_md5 = get_remote_files_md5(cfg, pod_name)
    remote_files, remote_dirs = get_remote_manifest(cfg, pod_name)

    files_to_upload_count = 0
    dirs_needed: set[str] = set()
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
                continue
            files_to_upload_count += 1
            dirs_needed.add(os.path.dirname(os.path.join(cfg.remote_path, rel)))

    local_files_set, local_dirs_set = collect_local_manifest(cfg.local_path, cfg.exclude_paths)
    prune_file_count = len(remote_files - local_files_set) if cfg.prune else 0
    prune_dir_count = len(remote_dirs - local_dirs_set) if cfg.prune else 0

    would_use_archive = is_remote_empty(cfg, pod_name) or files_to_upload_count > cfg.compress_threshold

    return SyncPlan(
        mode="incremental",
        local_file_count=local_file_count,
        local_empty_dir_count=local_empty_dir_count,
        remote_file_count=len(remote_files),
        remote_dir_count=len(remote_dirs),
        files_to_upload_count=files_to_upload_count,
        dirs_to_create_count=len(dirs_needed) + local_empty_dir_count,
        prune_file_count=prune_file_count,
        prune_dir_count=prune_dir_count,
        would_use_archive=would_use_archive,
    )


def _print_plan(plan: SyncPlan, cfg: SyncConfig) -> None:
    logger.info("=" * 60)
    logger.info("dry-run sync plan")
    logger.info("=" * 60)
    logger.info(f"mode:                  {plan.mode}")
    logger.info(f"local files:           {plan.local_file_count}")
    logger.info(f"local empty dirs:      {plan.local_empty_dir_count}")
    logger.info(f"remote files:          {plan.remote_file_count}")
    logger.info(f"remote dirs:           {plan.remote_dir_count}")
    logger.info(f"files to upload:       {plan.files_to_upload_count}")
    logger.info(f"dirs to create:        {plan.dirs_to_create_count}")
    logger.info(f"remote files to prune: {plan.prune_file_count if cfg.prune else 0}")
    logger.info(f"remote dirs to prune:  {plan.prune_dir_count if cfg.prune else 0}")
    logger.info(f"use archive path:      {plan.would_use_archive}")
    logger.info("=" * 60)


def _prune_remote_extras(cfg: SyncConfig, pod_name: str) -> None:
    if not cfg.prune:
        logger.info("startup prune disabled")
        return

    local_files, local_dirs = collect_local_manifest(cfg.local_path, cfg.exclude_paths)
    remote_files, remote_dirs = get_remote_manifest(cfg, pod_name)

    extra_files = sorted(remote_files - local_files)
    extra_dirs = sorted((remote_dirs - local_dirs), key=lambda x: x.count("/"), reverse=True)

    if not extra_files and not extra_dirs:
        logger.info("startup prune: no remote extras found")
        return

    logger.info(f"startup prune: deleting {len(extra_files)} files and {len(extra_dirs)} dirs")

    for rel in extra_files:
        _delete_remote_path(
            cfg,
            pod_name,
            os.path.join(cfg.remote_path, rel),
            is_dir=False,
            display_name=rel,
        )

    for rel in extra_dirs:
        _delete_remote_path(
            cfg,
            pod_name,
            os.path.join(cfg.remote_path, rel),
            is_dir=True,
            display_name=rel,
        )


def compress_and_upload(
    cfg: SyncConfig,
    pod_name: str,
    tmp_dir: str,
    project_name: str,
    label: str = "sync",
) -> tuple[float, float, float]:
    tar_path = os.path.join(tmp_dir, "sync_upload.tar.gz")
    chunk_files: list[str] = []
    remote_parts: list[str] = []
    remote_tar = os.path.join(cfg.remote_parent_path, "sync_upload.tar.gz")
    remote_stage = os.path.join(cfg.remote_parent_path, f".{project_name}.sync_stage")
    remote_backup = os.path.join(cfg.remote_parent_path, f".{project_name}.sync_backup")

    try:
        logger.info("compressing local directory...")
        t0 = time.time()
        compress_dir(cfg.local_path, tar_path, cfg.exclude_paths, cfg.debug)
        compress_time = time.time() - t0
        tar_size = os.path.getsize(tar_path)
        logger.success(f"archive size: {format_file_size(tar_size)} ({compress_time:.2f}s)")

        logger.info("splitting archive into dynamic chunks...")
        chunk_files, chunk_hashes = _split_archive(tar_path, tmp_dir, project_name, cfg)
        if not chunk_files:
            raise RuntimeError("no archive shards generated")
        approx_chunk_size = max(1, math.ceil(tar_size / len(chunk_files)))
        logger.info(f"chunk count: {len(chunk_files)}, chunk size approx: {format_file_size(approx_chunk_size)}")

        items = []
        for idx, chunk_path in enumerate(chunk_files):
            remote_chunk = os.path.join(cfg.remote_parent_path, os.path.basename(chunk_path))
            remote_parts.append(remote_chunk)
            items.append(
                UploadItem(
                    local_path=chunk_path,
                    remote_path=remote_chunk,
                    display_name=f"chunk {idx}",
                )
            )

        ok, fail, upload_time = _upload_items_parallel(
            cfg, pod_name, items, desc_prefix="upload chunk", timeout=300, retries=1
        )
        if fail:
            raise subprocess.CalledProcessError(0, "chunk upload")
        logger.success(f"all chunks uploaded ({upload_time:.2f}s, ok={ok})")

        logger.info("verifying remote chunk hashes...")
        md5_script = "for f in " + " ".join(shlex.quote(p) for p in remote_parts) + "; do md5sum $f 2>/dev/null || echo ERROR; done"
        md5_result = run_local_cmd(exec_cmd(cfg, pod_name, md5_script), debug=cfg.debug, desc="remote md5", timeout=120, check=False)

        remote_md5s: dict[int, str] = {}
        for line in md5_result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] != "ERROR":
                md5_val, file_path = parts[0], parts[1]
                try:
                    idx_part = os.path.basename(file_path).replace(f"{project_name}_sync_part_", "").replace(".tar.gz", "")
                    remote_md5s[int(idx_part)] = md5_val
                except ValueError:
                    pass

        mismatch = [idx for idx in range(len(chunk_files)) if remote_md5s.get(idx) != chunk_hashes.get(idx)]
        if mismatch:
            logger.error(f"chunk hash mismatch: {mismatch}")
            cleanup_remote_shards(cfg, pod_name, remote_parts)
            raise subprocess.CalledProcessError(0, "chunk hash mismatch")

        logger.success("all chunk hashes verified")

        run_local_cmd(exec_cmd(cfg, pod_name, f"rm -f {shlex.quote(remote_tar)}"), debug=cfg.debug, desc="cleanup remote tar", timeout=60, check=False)

        logger.info("merging remote chunks...")
        merge_start = time.time()
        run_local_cmd(exec_cmd(cfg, pod_name, f"cat {' '.join(shlex.quote(p) for p in remote_parts)} > {shlex.quote(remote_tar)}"), debug=cfg.debug, desc="merge chunks", timeout=120)
        logger.success(f"merge done ({time.time() - merge_start:.2f}s)")

        cleanup_remote_shards(cfg, pod_name, remote_parts)

        logger.info("extracting archive into remote staging dir...")
        extract_start = time.time()
        extract_script = (
            f"rm -rf {shlex.quote(remote_stage)} {shlex.quote(remote_backup)} && "
            f"mkdir -p {shlex.quote(remote_stage)} && "
            f"tar -xzf {shlex.quote(remote_tar)} -C {shlex.quote(remote_stage)} && "
            f"rm -f {shlex.quote(remote_tar)}"
        )
        run_local_cmd(exec_cmd(cfg, pod_name, extract_script), debug=cfg.debug, desc=f"{label} stage extract", timeout=1800)

        if label == "forced-full":
            # In forced-full mode: delete all files in remote_path (not the directory itself),
            # ignore errors for non-existent files, then recreate the directory
            switch_script = (
                f"rm -rf {shlex.quote(remote_backup)} && "
                f"if [ -d {shlex.quote(cfg.remote_path)} ]; then rm -rf {shlex.quote(cfg.remote_path)}/* 2>/dev/null || true; fi && "
                f"mkdir -p {shlex.quote(cfg.remote_path)} && "
                f"mv {shlex.quote(remote_stage)}/* {shlex.quote(cfg.remote_path)}/ && "
                f"rm -rf {shlex.quote(remote_stage)} {shlex.quote(remote_backup)}"
            )
        else:
            # In normal mode: move staging dir to replace the entire remote_path directory
            switch_script = (
                f"rm -rf {shlex.quote(remote_backup)} && "
                f"if [ -e {shlex.quote(cfg.remote_path)} ]; then mv {shlex.quote(cfg.remote_path)} {shlex.quote(remote_backup)}; fi && "
                f"mv {shlex.quote(remote_stage)} {shlex.quote(cfg.remote_path)} && "
                f"rm -rf {shlex.quote(remote_backup)}"
            )
        run_local_cmd(exec_cmd(cfg, pod_name, switch_script), debug=cfg.debug, desc=f"{label} stage switch", timeout=600)
        extract_time = time.time() - extract_start
        logger.success(f"stage extract + switch done ({extract_time:.2f}s)")

        return compress_time, upload_time, extract_time
    finally:
        cleanup_local_files([tar_path, *chunk_files], debug=cfg.debug)


def _log_timing(label: str, compress_time: float, upload_time: float, extract_time: float, total_time: float) -> None:
    logger.info("\n" + "=" * 60)
    logger.info(f"timing: {label}")
    logger.info("=" * 60)
    logger.info(f"compress: {compress_time:.2f}s")
    logger.info(f"upload:   {upload_time:.2f}s")
    logger.info(f"extract:  {extract_time:.2f}s")
    logger.info(f"total:    {total_time:.2f}s")
    logger.info("=" * 60)


def _batch_mkdir(cfg: SyncConfig, pod_name: str, dirs: set[str]) -> None:
    if not dirs:
        return
    sorted_dirs = sorted(dirs)
    leaf_dirs = [d for d in sorted_dirs if not any(other != d and other.startswith(d + "/") for other in sorted_dirs)]
    _mkdir_remote_dirs(cfg, pod_name, leaf_dirs, desc="mkdir remote dirs")


def _concurrent_upload(cfg: SyncConfig, pod_name: str, files_to_upload: list[tuple[str, str]]) -> None:
    items = [
        UploadItem(local_path=fp, remote_path=os.path.join(cfg.remote_path, rel), display_name=rel)
        for fp, rel in files_to_upload
    ]
    ok, fail, _ = _upload_items_parallel(cfg, pod_name, items, desc_prefix="upload file", timeout=1800, retries=2)
    logger.info(f"upload stats: ok={ok}, fail={fail}")


def _sync_empty_dirs_incremental(cfg: SyncConfig, pod_name: str) -> None:
    empty_dirs = collect_empty_dirs(cfg.local_path, cfg.exclude_paths)
    if not empty_dirs:
        logger.info("no empty dirs to sync")
        return
    remote_dirs = [os.path.join(cfg.remote_path, rel) for rel in empty_dirs]
    logger.info(f"syncing {len(remote_dirs)} empty dirs")
    _mkdir_remote_dirs(cfg, pod_name, remote_dirs, desc="sync empty dirs")


def upload_initial_files(cfg: SyncConfig, pod_name: str, project_name: str) -> None:
    start = time.time()

    try:
        run_local_cmd(exec_cmd(cfg, pod_name, f"mkdir -p {shlex.quote(cfg.remote_path)}"), debug=cfg.debug, desc="ensure remote dir", timeout=120, retries=1)
    except subprocess.CalledProcessError:
        logger.error("failed to ensure remote dir")
        return

    logger.info("checking remote directory...")
    if is_remote_empty(cfg, pod_name):
        logger.info("remote is empty, using full archive upload")
        with tempfile.TemporaryDirectory() as tmp:
            ct, ut, et = compress_and_upload(cfg, pod_name, tmp, project_name, label="initial")
        _log_timing("initial full sync", ct, ut, et, time.time() - start)
        logger.success("initial sync done")
        return

    logger.info("collecting remote md5 hashes...")
    remote_md5 = get_remote_files_md5(cfg, pod_name)
    logger.info(f"remote files: {len(remote_md5)}")

    files_to_upload: list[tuple[str, str]] = []
    files_skipped = 0
    dirs_needed: set[str] = set()

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

    logger.info(f"summary: remote={len(remote_md5)} local={files_skipped + len(files_to_upload)} upload={len(files_to_upload)}")

    if len(files_to_upload) > cfg.compress_threshold:
        logger.info(f"upload count > {cfg.compress_threshold}, using fast archive path")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ct, ut, et = compress_and_upload(cfg, pod_name, tmp, project_name, label="fast")
            _log_timing("fast archive sync", ct, ut, et, time.time() - start)
            logger.success("initial sync done")
            return
        except subprocess.CalledProcessError:
            logger.error("fast archive path failed, falling back to incremental upload")

    if files_to_upload:
        _batch_mkdir(cfg, pod_name, dirs_needed)
        _concurrent_upload(cfg, pod_name, files_to_upload)
    else:
        logger.info("nothing to upload")

    _sync_empty_dirs_incremental(cfg, pod_name)
    _prune_remote_extras(cfg, pod_name)
    logger.info(f"initial sync finished in {time.time() - start:.2f}s")
    logger.success("initial sync done")


_TEMP_SUFFIXES = ("~", ".swp", ".swo", ".swn", ".tmp", ".bak", ".temp")
_TEMP_PREFIXES = (".#", "~")


def _is_temp_file(name: str) -> bool:
    return any(name.endswith(s) for s in _TEMP_SUFFIXES) or any(name.startswith(p) for p in _TEMP_PREFIXES) or ".tmp." in name or name.endswith("#")


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, cfg: SyncConfig, pod_name: str, executor: ThreadPoolExecutor):
        self.cfg = cfg
        self.pod_name = pod_name
        self.executor = executor
        self.processing_paths: dict[str, Any] = {}
        self.debounce_timers: dict[str, threading.Timer] = {}
        self.desired_actions: dict[str, tuple[str, bool]] = {}
        self.lock = threading.Lock()

    def _should_skip(self, path: str) -> bool:
        name = os.path.basename(path)
        if any(part.startswith(".") for part in path.split(os.sep)):
            return True
        if _is_temp_file(name):
            return True
        rel = os.path.relpath(path, self.cfg.local_path)
        return is_excluded(rel, self.cfg.exclude_paths)

    def _remote_path_for_local(self, path: str) -> str:
        rel = os.path.relpath(path, self.cfg.local_path)
        return os.path.join(self.cfg.remote_path, rel)

    def _cancel_debounce(self, path: str) -> None:
        old_timer = self.debounce_timers.pop(path, None)
        if old_timer and old_timer.is_alive():
            old_timer.cancel()

    def _is_processing(self, path: str) -> bool:
        fut = self.processing_paths.get(path)
        return bool(fut and not fut.done())

    def _set_desired_action(self, path: str, action: str, is_dir: bool) -> None:
        with self.lock:
            self.desired_actions[path] = (action, is_dir)

    def _get_desired_action(self, path: str) -> tuple[str, bool] | None:
        with self.lock:
            return self.desired_actions.get(path)

    def _clear_desired_action_if_matches(self, path: str, action: str, is_dir: bool) -> None:
        with self.lock:
            current = self.desired_actions.get(path)
            if current == (action, is_dir):
                self.desired_actions.pop(path, None)

    def _schedule_reconcile(self, path: str) -> None:
        if self._is_processing(path):
            return
        desired = self._get_desired_action(path)
        if not desired:
            return
        action, is_dir = desired
        if action == "upload":
            self.processing_paths[path] = self.executor.submit(self._upload_file, path)
        elif action == "delete":
            self.processing_paths[path] = self.executor.submit(self._delete_path, path, is_dir)
        elif action == "mkdir":
            self.processing_paths[path] = self.executor.submit(self._mkdir_remote_dir, path)

    def _schedule_dir_recursive_sync(self, dir_path: str) -> None:
        if not os.path.isdir(dir_path):
            return
        self._ensure_remote_dir(dir_path)
        files = collect_syncable_files_under(dir_path, self.cfg.local_path, self.cfg.exclude_paths)
        if files:
            logger.info(f"directory move/create detected, resyncing subtree: {os.path.relpath(dir_path, self.cfg.local_path)} ({len(files)} files)")
            _concurrent_upload(self.cfg, self.pod_name, files)
        empty_dirs = collect_empty_dirs(dir_path, self.cfg.exclude_paths)
        if empty_dirs:
            remote_dirs = [os.path.join(self.cfg.remote_path, rel) for rel in empty_dirs]
            _mkdir_remote_dirs(self.cfg, self.pod_name, remote_dirs, desc="sync moved empty dirs")

    def on_modified(self, event):
        if not event.is_directory and not self._should_skip(event.src_path):
            self.upload_file(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            if not self._should_skip(event.src_path):
                self._schedule_dir_recursive_sync(event.src_path)
            return
        if not self._should_skip(event.src_path):
            self.upload_file(event.src_path)

    def on_deleted(self, event):
        if self._should_skip(event.src_path):
            return
        self.delete_remote_path(event.src_path, is_dir=event.is_directory)

    def on_moved(self, event):
        src = event.src_path
        dest = event.dest_path
        src_in_scope = src.startswith(self.cfg.local_path) and not self._should_skip(src)
        dest_in_scope = dest.startswith(self.cfg.local_path) and not self._should_skip(dest)

        if src_in_scope and not dest_in_scope:
            self.delete_remote_path(src, is_dir=event.is_directory)
            return

        if not src_in_scope and dest_in_scope:
            if event.is_directory:
                self._schedule_dir_recursive_sync(dest)
            else:
                self.upload_file(dest)
            return

        if not src_in_scope and not dest_in_scope:
            return

        self.delete_remote_path(src, is_dir=event.is_directory)
        if event.is_directory:
            self._schedule_dir_recursive_sync(dest)
        else:
            self.upload_file(dest)

    def upload_file(self, file_path: str) -> None:
        rel = os.path.relpath(file_path, self.cfg.local_path)
        self._set_desired_action(file_path, "upload", False)
        self._cancel_debounce(file_path)

        logger.info(f"file changed: {rel}, uploading in {self.cfg.debounce_seconds}s")
        timer = threading.Timer(self.cfg.debounce_seconds, self._debounced_upload, args=[file_path])
        self.debounce_timers[file_path] = timer
        timer.start()

    def delete_remote_path(self, path: str, *, is_dir: bool) -> None:
        rel = os.path.relpath(path, self.cfg.local_path)
        self._cancel_debounce(path)
        self._set_desired_action(path, "delete", is_dir)
        if self._is_processing(path):
            logger.info(f"path busy, delete queued as final state: {rel}")
            return
        self._schedule_reconcile(path)

    def _ensure_remote_dir(self, dir_path: str) -> None:
        self._cancel_debounce(dir_path)
        self._set_desired_action(dir_path, "mkdir", True)
        if self._is_processing(dir_path):
            return
        self._schedule_reconcile(dir_path)

    def _mkdir_remote_dir(self, local_dir_path: str) -> None:
        rel = os.path.relpath(local_dir_path, self.cfg.local_path)
        remote_dir = self._remote_path_for_local(local_dir_path)
        try:
            desired = self._get_desired_action(local_dir_path)
            if desired != ("mkdir", True):
                return
            _mkdir_remote_dirs(self.cfg, self.pod_name, [remote_dir], desc=f"mkdir {rel}")
        finally:
            self.processing_paths.pop(local_dir_path, None)
            self._clear_desired_action_if_matches(local_dir_path, "mkdir", True)
            self._schedule_reconcile(local_dir_path)

    def _delete_path(self, path: str, is_dir: bool) -> None:
        rel = os.path.relpath(path, self.cfg.local_path)
        try:
            desired = self._get_desired_action(path)
            if desired != ("delete", is_dir):
                return
            _delete_remote_path(
                self.cfg,
                self.pod_name,
                self._remote_path_for_local(path),
                is_dir=is_dir,
                display_name=rel,
            )
        finally:
            self.processing_paths.pop(path, None)
            self._clear_desired_action_if_matches(path, "delete", is_dir)
            self._schedule_reconcile(path)

    def _debounced_upload(self, file_path: str) -> None:
        self.debounce_timers.pop(file_path, None)
        desired = self._get_desired_action(file_path)
        if desired != ("upload", False):
            return
        if self._is_processing(file_path):
            return
        self._schedule_reconcile(file_path)

    def _upload_file(self, file_path: str) -> None:
        rel = os.path.relpath(file_path, self.cfg.local_path)
        start = time.time()
        try:
            desired = self._get_desired_action(file_path)
            if desired != ("upload", False):
                return
            if not os.path.exists(file_path):
                logger.warning(f"file disappeared before upload: {rel}")
                self._set_desired_action(file_path, "delete", False)
                return

            if not _wait_for_file_stable(file_path):
                logger.warning(f"file did not become stable in time, skipping this round: {rel}")
                # File was unstable or disappeared during stability check.
                # Clear the desired action so next modification event can retry fresh.
                # This prevents accidental deletion of remote files due to editor temporary deletions.
                self._clear_desired_action_if_matches(file_path, "upload", False)
                return

            remote_dir = os.path.dirname(os.path.join(self.cfg.remote_path, rel))
            _mkdir_remote_dirs(self.cfg, self.pod_name, [remote_dir], desc=f"mkdir parent for {rel}")

            desired = self._get_desired_action(file_path)
            if desired != ("upload", False):
                return
            if not os.path.exists(file_path):
                # File vanished after stability check confirmed it exists.
                # This is a genuine deletion that should be synced to remote.
                self._set_desired_action(file_path, "delete", False)
                return

            item = UploadItem(
                local_path=file_path,
                remote_path=os.path.join(self.cfg.remote_path, rel),
                display_name=rel,
            )
            ok = _upload_single_item(
                self.cfg,
                self.pod_name,
                item,
                desc_prefix="realtime upload",
                timeout=1800,
                retries=2,
            )
            if ok:
                try:
                    sz = format_file_size(os.path.getsize(file_path))
                except OSError:
                    sz = "unknown"
                logger.success(f"file synced: {rel} ({sz}, {time.time() - start:.2f}s)")
            else:
                logger.error(f"file sync failed: {rel} ({time.time() - start:.2f}s)")
        except subprocess.CalledProcessError as e:
            logger.error(f"file sync failed: {rel} - exit code: {e.returncode} ({time.time() - start:.2f}s)")
        finally:
            self.processing_paths.pop(file_path, None)
            self._clear_desired_action_if_matches(file_path, "upload", False)
            self._schedule_reconcile(file_path)


def get_config_path(project_name: str) -> Path:
    config_dir = Path.home() / ".sync2pod" / project_name
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "sync_config.json"


def load_config(project_name: str) -> dict[str, Any]:
    path = get_config_path(project_name)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(project_name: str, config: dict[str, Any]) -> None:
    with open(get_config_path(project_name), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def list_projects() -> None:
    sync2pod_dir = Path.home() / ".sync2pod"
    if not sync2pod_dir.exists():
        logger.info("no project configs found")
        logger.info("init: sync_local_to_pod --init-config --local-path <path>")
        return

    projects = []
    for d in sync2pod_dir.iterdir():
        cfg_file = d / "sync_config.json"
        if d.is_dir() and cfg_file.exists():
            try:
                with open(cfg_file, encoding="utf-8") as f:
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
        logger.info("no valid project configs found")
        return

    logger.info("=" * 60)
    logger.info(f"configured projects ({len(projects)})")
    logger.info("=" * 60)
    for i, p in enumerate(projects, 1):
        logger.info(f"{i}. name: {p['name']}")
        logger.info(f"   local: {p['local_path']}")
        logger.info(f"   remote parent: {p['remote_parent_path']}")
        logger.info(f"   cluster: {p['cluster']}  namespace: {p['namespace']}")
    logger.info("=" * 60)
    logger.info("sync_local_to_pod --project <name>")


_EXAMPLE_CONFIG = {
    "cluster": "908",
    "namespace": "sdsnushare01-dev",
    "pod_label": "serviceName=hk-develop",
    "remote_parent_path": "/mnt/gfs-develop/workspace",
    "local_path": "__REPLACE__",
    "compress_threshold": 100,
    "max_workers": 10,
    "debug": False,
    "show_concurrency": False,
    "no_watch": False,
    "skip_verify": False,
    "debounce_seconds": 1.0,
    "prune": True,
    "upload_chunk_count": 6,
    "target_chunk_size_mb": 64,
    "exclude_paths": ["node_modules", "*.log", "dist/build"],
}


def init_config(project_name: str, local_path: str) -> None:
    config_path = get_config_path(project_name)
    if config_path.exists():
        cfg = load_config(project_name)
        if not cfg.get("local_path"):
            cfg["local_path"] = local_path
            save_config(project_name, cfg)
            logger.success("config file updated (local_path added)")
        else:
            logger.info("config file already exists")
        logger.info(f"file: {config_path}")
        logger.info(f"edit: vim {config_path}")
        logger.info(f"run:  sync_local_to_pod --project {project_name}")
        return

    example = {**_EXAMPLE_CONFIG, "local_path": local_path}
    save_config(project_name, example)
    logger.success("config file created")
    logger.info(f"file: {config_path}")
    logger.info(json.dumps(example, indent=4, ensure_ascii=False))
    logger.info(f"edit: vim {config_path}")
    logger.info(f"run:  sync_local_to_pod --project {project_name}")


def _run_sync(project_name: str, force_full_sync: bool, skip_verify_flag: bool, dry_run: bool) -> None:
    config_path = get_config_path(project_name)
    raw = load_config(project_name)

    try:
        cfg = SyncConfig.from_dict(raw)
    except ValueError as e:
        logger.error(f"config error: {e}")
        logger.info(f"edit config: {config_path}")
        sys.exit(1)

    if skip_verify_flag:
        cfg.skip_verify = True

    setup_logging(verbose=cfg.debug, fmt="{time:HH:mm:ss.SSS} | {level:<8} | {message}", colorize=False)

    if not cfg.skip_verify and not dry_run:
        logger.info("=" * 60)
        logger.info("sync config check")
        logger.info("=" * 60)
        logger.info(f"config file:           {config_path}")
        logger.info(f"cluster:               {cfg.cluster}")
        logger.info(f"namespace:             {cfg.namespace}")
        logger.info(f"pod label:             {cfg.pod_label}")
        logger.info(f"remote parent path:    {cfg.remote_parent_path}")
        logger.info(f"remote sync path:      {cfg.remote_path}")
        logger.info(f"local path:            {cfg.local_path}")
        logger.info(f"prune remote extras:   {cfg.prune}")
        logger.info(f"compress threshold:    {cfg.compress_threshold}")
        logger.info(f"max shard count:       {cfg.upload_chunk_count}")
        logger.info(f"target shard size MB:  {cfg.target_chunk_size_mb}")
        logger.info("=" * 60)
        logger.info("press Enter to continue, Ctrl+C to cancel")
        try:
            input()
        except KeyboardInterrupt:
            logger.error("user cancelled")
            sys.exit(0)
        logger.success("confirmed, starting sync")

    if not os.path.exists(cfg.local_path):
        logger.error(f"local path does not exist: {cfg.local_path}")
        sys.exit(1)

    try:
        pod_name = select_running_pod_by_label(cfg)
    except Exception as e:
        logger.error(f"pod selection failed: {e}")
        sys.exit(1)
    logger.info(f"target pod: {pod_name}")

    try:
        check_remote_capabilities(cfg, pod_name)
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)

    if dry_run:
        plan = _plan_sync(cfg, pod_name, force_full_sync)
        _print_plan(plan, cfg)
        logger.success("dry-run complete")
        return

    if force_full_sync:
        logger.info("forced full sync mode")
        t0 = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                ct, ut, et = compress_and_upload(cfg, pod_name, tmp, project_name, label="forced-full")
            except subprocess.CalledProcessError:
                logger.error("forced full sync failed")
                sys.exit(1)
        _log_timing("forced full sync", ct, ut, et, time.time() - t0)
    else:
        file_count = count_files(cfg.local_path, cfg.exclude_paths)
        logger.info(f"local files: {file_count}, starting md5 incremental sync")
        upload_initial_files(cfg, pod_name, project_name)

    if cfg.no_watch:
        logger.success("sync done (watch disabled)")
        return

    logger.info(f"watching file changes... workers={cfg.max_workers}, debounce={cfg.debounce_seconds}s")
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        handler = FileChangeHandler(cfg, pod_name, executor)
        observer = Observer()
        observer.schedule(handler, path=cfg.local_path, recursive=True)
        observer.start()
        logger.success(f"watch started: {cfg.local_path}")
        logger.info("press Ctrl+C to stop")
        try:
            while True:
                time.sleep(30)
                if cfg.show_concurrency:
                    active = len([f for f in handler.processing_paths.values() if not f.done()])
                    if active:
                        logger.info(f"active tasks: {active}/{cfg.max_workers}")
        except KeyboardInterrupt:
            logger.info("stopping watcher...")
            observer.stop()
        observer.join()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="sync local directory to a K8s pod",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sync_local_to_pod --init-config --local-path /path/to/project
  sync_local_to_pod --list-projects
  sync_local_to_pod --project heketi
  sync_local_to_pod --project heketi --force
  sync_local_to_pod --project heketi --dry-run
""",
    )
    parser.add_argument("--init-config", action="store_true", help="create config file")
    parser.add_argument("--list-projects", action="store_true", help="list configured projects")
    parser.add_argument("--project", help="project name")
    parser.add_argument("--local-path", help="local directory path for init")
    parser.add_argument("--force", action="store_true", help="force full sync")
    parser.add_argument("--skip-verify", action="store_true", help="skip config confirmation")
    parser.add_argument("--dry-run", action="store_true", help="show sync plan without making changes")
    args = parser.parse_args()

    setup_logging(verbose=False, fmt="{time:HH:mm:ss.SSS} | {level:<8} | {message}", colorize=False)

    if args.list_projects:
        list_projects()
        return

    if args.init_config:
        if not args.local_path:
            logger.error("--init-config requires --local-path")
            sys.exit(1)
        local_path = os.path.abspath(args.local_path)
        if not os.path.exists(local_path):
            logger.error(f"local path does not exist: {local_path}")
            sys.exit(1)
        init_config(os.path.basename(os.path.normpath(local_path)), local_path)
        return

    if not args.project:
        logger.error("please specify an operation mode")
        logger.info("init:   sync_local_to_pod --init-config --local-path <path>")
        logger.info("list:   sync_local_to_pod --list-projects")
        logger.info("sync:   sync_local_to_pod --project <name>")
        sys.exit(1)

    project_name = args.project
    if os.path.isabs(project_name) or "/" in project_name:
        logger.error("--project must be a project name, not a path")
        sys.exit(1)

    sync2pod_dir = Path.home() / ".sync2pod"
    existing = [d.name for d in sync2pod_dir.iterdir() if d.is_dir() and (d / "sync_config.json").exists()] if sync2pod_dir.exists() else []

    if project_name not in existing:
        logger.error(f"project '{project_name}' does not exist")
        if existing:
            for p in existing:
                logger.info(f"  - {p}")
        else:
            logger.info("init: sync_local_to_pod --init-config --local-path <path>")
        sys.exit(1)

    _run_sync(project_name, force_full_sync=args.force, skip_verify_flag=args.skip_verify, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
