#!/usr/bin/env python3
"""
bisync — 本地双向文件同步工具（基于 Unison）

使用 Unison 实现 Mac 本地两个目录的双向同步：
  1. 校验 source_dir 存在
  2. 首次同步：source_dir 覆盖更新 target_dir（source 优先）
  3. 持续监控：双向实时同步
"""

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from loguru import logger


# ========== 常量 ==========

UNISON_BIN = os.environ.get("UNISON_BIN", "unison")
STATE_DIR = Path.home() / ".bisync"


# ========== 日志配置 ==========

def setup_logging(verbose: bool = False) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True,
    )


# ========== 状态文件 ==========

def get_profile_name(source_dir: Path, target_dir: Path, name: str | None) -> str:
    """生成同步对的唯一标识，用于状态文件目录名。"""
    if name:
        return name
    combined = f"{source_dir.resolve()}::{target_dir.resolve()}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]


def get_state_path(profile: str) -> Path:
    return STATE_DIR / profile / "state.json"


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state_path: Path, data: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ========== Unison 工具 ==========

def find_unison() -> str:
    """定位 unison 可执行文件，找不到则退出。"""
    import shutil

    # 优先使用 UNISON_BIN 环境变量
    if UNISON_BIN != "unison":
        if Path(UNISON_BIN).is_file():
            return UNISON_BIN
        logger.error(f"❌ UNISON_BIN 指向的路径不存在: {UNISON_BIN}")
        sys.exit(1)

    resolved = shutil.which("unison")
    if resolved:
        return resolved

    # 尝试已知安装路径
    for candidate in [
        Path.home() / ".opam/default/bin/unison",
        Path("/usr/local/bin/unison"),
        Path("/opt/homebrew/bin/unison"),
    ]:
        if candidate.is_file():
            return str(candidate)

    logger.error("❌ 未找到 unison，请先安装: brew install unison 或 opam install unison")
    sys.exit(1)


def run_unison(
    unison: str,
    source_dir: Path,
    target_dir: Path,
    extra_args: list,
    dry_run: bool = False,
    capture_stderr: bool = False,
) -> tuple:
    """执行 unison 命令，返回 (退出码, stderr文本)。"""
    cmd = [
        unison,
        str(source_dir),
        str(target_dir),
        "-auto",
        "-batch",
        "-ui", "text",
    ] + extra_args

    if dry_run:
        logger.info(f"[dry-run] 将执行: {' '.join(cmd)}")
        return 0, ""

    logger.debug(f"执行: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            stderr=subprocess.PIPE if capture_stderr else None,
            text=True,
        )
        stderr = result.stderr or ""
        return result.returncode, stderr
    except FileNotFoundError:
        logger.error(f"❌ 找不到 unison 可执行文件: {unison}")
        sys.exit(1)


# ========== 同步阶段 ==========

def do_initial_sync(unison: str, source_dir: Path, target_dir: Path, dry_run: bool) -> bool:
    """首次同步：以 source_dir 为准覆盖更新 target_dir。"""
    logger.info(f"🚀 执行首次同步（source 优先）: {source_dir} → {target_dir}")
    rc, _ = run_unison(
        unison,
        source_dir,
        target_dir,
        extra_args=["-force", str(source_dir)],
        dry_run=dry_run,
    )
    # unison 退出码: 0=成功, 1=有文件跳过(非致命), 2=致命错误
    if rc == 2:
        logger.error(f"❌ 首次同步失败（退出码: {rc}）")
        return False
    logger.info("✅ 首次同步完成")
    return True


DEFAULT_POLL_INTERVAL = 3  # 秒
FSWATCH_DEBOUNCE = 1.0    # 秒，合并短时间内的多次变更


def do_watch_sync(
    unison: str,
    source_dir: Path,
    target_dir: Path,
    dry_run: bool,
    interval: int = DEFAULT_POLL_INTERVAL,
) -> None:
    """持续双向监控同步（阻塞直到用户中断）。

    优先级：
      1. unison -repeat watch（依赖 unison-fsmonitor，实时）
      2. fswatch + unison 触发（实时，macOS 原生 FSEvents）
      3. unison -repeat <N>（轮询，兜底）
    """
    if dry_run:
        logger.info("[dry-run] 跳过监控模式启动")
        return

    logger.info(f"👀 启动双向监控: {source_dir} ↔ {target_dir}（Ctrl+C 退出）")

    # 1. 先尝试 unison 原生 watch 模式
    rc, stderr = run_unison(
        unison,
        source_dir,
        target_dir,
        extra_args=["-repeat", "watch"],
        capture_stderr=True,
    )
    if not (rc != 0 and "No file monitoring helper" in (stderr or "")):
        return  # 成功退出或非 fsmonitor 错误，直接返回

    # 2. 尝试 fswatch 实时监控
    fswatch_bin = shutil.which("fswatch")
    if fswatch_bin:
        logger.info(f"✅ 使用 fswatch 实时监控（FSEvents）")
        _watch_with_fswatch(unison, fswatch_bin, source_dir, target_dir)
        return

    # 3. 兜底：轮询模式
    logger.warning(f"⚠️  fswatch 未找到，降级到轮询模式（每 {interval} 秒检测一次）")
    logger.info("提示: brew install fswatch 可获得实时监控")
    run_unison(
        unison,
        source_dir,
        target_dir,
        extra_args=["-repeat", str(interval)],
    )


def _watch_with_fswatch(
    unison: str,
    fswatch_bin: str,
    source_dir: Path,
    target_dir: Path,
) -> None:
    """用 fswatch 监听文件变化，防抖后触发 unison 双向同步。"""
    sync_lock = threading.Lock()
    pending = threading.Event()
    stop_event = threading.Event()

    def sync_worker() -> None:
        while not stop_event.is_set():
            pending.wait(timeout=1.0)
            if not pending.is_set():
                continue
            pending.clear()
            # 等待防抖窗口，若期间有新事件则重置
            time.sleep(FSWATCH_DEBOUNCE)
            if pending.is_set():
                continue
            with sync_lock:
                logger.debug("🔄 检测到变更，触发同步")
                rc, _ = run_unison(unison, source_dir, target_dir, extra_args=[])
                if rc == 2:
                    logger.error("❌ 同步失败")

    t = threading.Thread(target=sync_worker, daemon=True)
    t.start()

    cmd = [
        fswatch_bin,
        "--recursive",
        "--event=Created", "--event=Updated",
        "--event=Removed", "--event=Renamed",
        "--event=MovedFrom", "--event=MovedTo",
        "--latency=0.5",
        str(source_dir),
        str(target_dir),
    ]
    logger.debug(f"fswatch 命令: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    try:
        for line in proc.stdout:
            line = line.strip()
            if line:
                logger.debug(f"变更: {line}")
                pending.set()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        proc.terminate()
        proc.wait()


# ========== 信号处理 ==========

def setup_signal_handlers() -> None:
    def _handler(sig, frame):
        logger.info("\n⏹  收到退出信号，停止同步监控")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


# ========== CLI ==========

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bisync",
        description="本地双向文件同步工具（基于 Unison）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  bisync.py ~/Documents/notes ~/Dropbox/notes
  bisync.py /data/project /backup/project --name my-project
  bisync.py ~/src ~/dst --reset      # 重置状态，重新执行首次同步
  bisync.py ~/src ~/dst --dry-run    # 预览同步内容，不实际修改
        """,
    )
    parser.add_argument("source_dir", help="源目录（必须已存在）")
    parser.add_argument("target_dir", help="目标目录（不存在时自动创建）")
    parser.add_argument(
        "--name",
        default=None,
        metavar="NAME",
        help="同步对名称（用于状态文件，默认由目录路径自动生成）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="重置同步状态，强制重新执行首次同步（source 覆盖 target）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：打印将执行的命令，不实际修改文件",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细日志（包含执行的命令）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        metavar="SEC",
        help=f"轮询间隔（秒），在 fsmonitor 不可用时使用（默认: {DEFAULT_POLL_INTERVAL}）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(verbose=args.verbose)
    setup_signal_handlers()

    source_dir = Path(args.source_dir).expanduser().resolve()
    target_dir = Path(args.target_dir).expanduser().resolve()

    # 1. 校验 source_dir
    if not source_dir.exists():
        logger.error(f"❌ source_dir 不存在: {source_dir}")
        sys.exit(1)
    if not source_dir.is_dir():
        logger.error(f"❌ source_dir 不是目录: {source_dir}")
        sys.exit(1)

    # 2. target_dir 不存在则自动创建
    if not target_dir.exists():
        if args.dry_run:
            logger.info(f"📁 [dry-run] target_dir 不存在，将创建: {target_dir}")
        else:
            logger.info(f"📁 target_dir 不存在，自动创建: {target_dir}")
            target_dir.mkdir(parents=True, exist_ok=True)

    # 3. 定位 unison
    unison = find_unison()
    logger.info(f"🔧 Unison: {unison}")
    logger.info(f"📂 source: {source_dir}")
    logger.info(f"📂 target: {target_dir}")

    # 4. 状态管理
    profile = get_profile_name(source_dir, target_dir, args.name)
    state_path = get_state_path(profile)
    state = load_state(state_path)

    if args.reset:
        logger.info("🔄 已重置同步状态，将重新执行首次同步")
        state = {}

    initial_done = state.get("initial_sync_done", False)

    # 5. 首次同步（source 优先）
    if not initial_done:
        success = do_initial_sync(unison, source_dir, target_dir, args.dry_run)
        if not success:
            sys.exit(1)
        if not args.dry_run:
            state["initial_sync_done"] = True
            state["source_dir"] = str(source_dir)
            state["target_dir"] = str(target_dir)
            save_state(state_path, state)
    else:
        logger.info("ℹ️  首次同步已完成，直接进入监控模式（使用 --reset 重新触发首次同步）")

    # 6. 持续双向监控
    do_watch_sync(unison, source_dir, target_dir, args.dry_run, interval=args.interval)


if __name__ == "__main__":
    main()
