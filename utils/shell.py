"""Shared shell / subprocess utilities.

Provides a unified local command runner with retry, timeout, and optional
login-shell wrapping so that commands executed from environments with minimal
PATH (e.g. uTools / Electron) still see the full user environment.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time

from loguru import logger


def cmd_repr(command: str | list[str]) -> str:
    """Human-readable representation of a command."""
    return command if isinstance(command, str) else shlex.join(command)


def run_local_cmd(
    command: str | list[str],
    *,
    use_login_shell: bool = False,
    timeout: int = 30,
    retries: int = 0,
    retry_delay: float = 1.0,
    check: bool = True,
    debug: bool = False,
    desc: str | None = None,
) -> subprocess.CompletedProcess:
    """Execute a command locally with retry support.

    Args:
        command: Command string or argument list.
        use_login_shell: Wrap command in a login shell with ``source ~/.zshrc``
            for full PATH + env vars (e.g. ``JIRA_API_TOKEN``).  Useful when
            running from environments with minimal PATH (uTools / Electron).
        timeout: Seconds before timeout per attempt.
        retries: Number of *extra* retry attempts (0 = single attempt).
        retry_delay: Seconds to wait between retries.
        check: Raise :class:`subprocess.CalledProcessError` on non-zero exit.
        debug: Log the command being executed.
        desc: Human-readable label for log messages.

    Returns:
        :class:`subprocess.CompletedProcess` with captured stdout / stderr.

    Raises:
        subprocess.TimeoutExpired: After all retries are exhausted.
        subprocess.CalledProcessError: When *check* is True and exit code != 0.
    """
    if use_login_shell:
        cmd_str = command if isinstance(command, str) else shlex.join(command)
        shell_path = os.environ.get("SHELL", "/bin/zsh")
        command = f"{shell_path} -l -c 'source ~/.zshrc >/dev/null 2>&1; {cmd_str}'"

    if debug:
        logger.debug(f"[cmd] {desc + ': ' if desc else ''}{cmd_repr(command)}")

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(
                command,
                shell=isinstance(command, str),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        except subprocess.TimeoutExpired as e:
            last_err = e
            logger.error(
                f"command timeout ({timeout}s)"
                f"{' - ' + desc if desc else ''}: {cmd_repr(command)}"
            )
        except subprocess.CalledProcessError as e:
            last_err = e
            stderr = (e.stderr or "").strip()
            msg = stderr or f"exit code: {e.returncode}"
            logger.error(f"command failed{' - ' + desc if desc else ''}: {msg}")

        if attempt < retries:
            logger.warning(
                f"retrying ({attempt + 1}/{retries})"
                f"{' - ' + desc if desc else ''}"
            )
            time.sleep(retry_delay)

    if last_err:
        raise last_err
    raise RuntimeError("unexpected run_local_cmd state")


def test_binary(
    bin_path: str,
    test_arg: str = "--help",
    timeout: int = 15,
    use_login_shell: bool = True,
) -> bool:
    """Test whether a binary is callable.

    Returns True on success, False on failure (details printed to stderr).
    """
    print(f"🔧 Testing command: {bin_path}", file=sys.stderr)
    try:
        result = run_local_cmd(
            f"{shlex.quote(bin_path)} {test_arg}",
            use_login_shell=use_login_shell,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            print(f"✅ Command works: {bin_path}", file=sys.stderr)
            return True
        print(f"❌ Command exited with code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"   stderr: {result.stderr.strip()}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out: {bin_path}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Error testing command: {e}", file=sys.stderr)
        return False
