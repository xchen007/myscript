"""Generic concurrent execution utilities.

Provides a thread-pool-based ``run_concurrent`` helper for I/O-bound tasks
such as subprocess calls, HTTP requests, etc.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar('T')
R = TypeVar('R')


def run_concurrent(
    items: Iterable[T],
    func: Callable[[T], R],
    *,
    max_workers: int = 5,
    progress: Callable[[int, int, T], None] | None = None,
) -> list[R]:
    """Execute *func* on every item concurrently, returning results in the
    original order.

    Args:
        items: Iterable of inputs to process.
        func: Callable that takes a single item and returns a result.
        max_workers: Maximum number of parallel threads.
        progress: Optional callback ``(completed, total, item)`` called after
            each item finishes (from any thread, serialisation is the caller's
            responsibility if needed).

    Returns:
        A list of results in the same order as *items*.  If *func* raises an
        exception for an item, the corresponding slot will be ``None``.
    """
    item_list = list(items)
    total = len(item_list)
    if total == 0:
        return []

    results: list[R | None] = [None] * total
    completed = 0

    with ThreadPoolExecutor(max_workers=min(max_workers, total)) as pool:
        future_to_idx = {
            pool.submit(func, item): (idx, item)
            for idx, item in enumerate(item_list)
        }
        for future in as_completed(future_to_idx):
            idx, item = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"⚠️  Error processing {item}: {e}", file=sys.stderr)
                results[idx] = None

            completed += 1
            if progress:
                progress(completed, total, item)

    return results  # type: ignore[return-value]
