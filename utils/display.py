"""Terminal display utilities — CJK-aware table formatting and hyperlinks."""

from __future__ import annotations

from typing import Any, Dict, List


def display_width(s: str) -> int:
    """Calculate display width accounting for CJK double-width characters."""
    width = 0
    for ch in s:
        cp = ord(ch)
        if (0x1100 <= cp <= 0x115F or
                0x2E80 <= cp <= 0x303E or
                0x3041 <= cp <= 0xA4CF or
                0xAC00 <= cp <= 0xD7AF or
                0xF900 <= cp <= 0xFAFF or
                0xFE10 <= cp <= 0xFE1F or
                0xFE30 <= cp <= 0xFE4F or
                0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6):
            width += 2
        else:
            width += 1
    return width


def pad_cell(s: str, width: int) -> str:
    """Right-pad string to *width* display columns, accounting for wide chars."""
    return s + ' ' * max(0, width - display_width(s))


def make_hyperlink(text: str, url: str) -> str:
    """Wrap *text* in an OSC 8 terminal hyperlink escape sequence."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def print_table(
    headers: List[str],
    rows: List[List[str]],
    title: str = "",
    col_overrides: Dict[int, int] | None = None,
    cell_formatters: Dict[int, Any] | None = None,
) -> None:
    """Print a formatted ASCII table with CJK-aware column widths.

    Args:
        headers: Column header strings.
        rows: List of row data (each row is a list of cell strings).
        title: Optional title printed above the table.
        col_overrides: ``{col_index: forced_width}`` to override auto-sizing.
        cell_formatters: ``{col_index: fn(raw_cell) -> formatted_str}``.
            Formatters may add invisible escape codes; width is always
            calculated from the raw cell value.
    """
    if not rows:
        return

    col_widths: list[int] = []
    for i, header in enumerate(headers):
        max_width = display_width(header)
        for row in rows:
            if i < len(row):
                max_width = max(max_width, display_width(str(row[i])))
        col_widths.append(max_width)

    if col_overrides:
        for idx, width in col_overrides.items():
            if 0 <= idx < len(col_widths):
                col_widths[idx] = width

    if title:
        print(f"\n{title}")

    sep_width = sum(col_widths) + len(headers) * 3 - 1

    header_row = " │ ".join(
        pad_cell(h, col_widths[i]) for i, h in enumerate(headers)
    )
    print(f" {header_row} ")
    print("─" * sep_width)

    for row in rows:
        cells: list[str] = []
        for i in range(len(headers)):
            raw = str(row[i]) if i < len(row) else ''
            padding = ' ' * max(0, col_widths[i] - display_width(raw))
            if cell_formatters and i in cell_formatters:
                cells.append(cell_formatters[i](raw) + padding)
            else:
                cells.append(raw + padding)
        print(f" {' │ '.join(cells)} ")

    print()
