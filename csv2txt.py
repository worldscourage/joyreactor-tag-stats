#!/usr/bin/env python3
"""Convert a CSV file into a human-readable plain-text file."""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from pathlib import Path


def display_width(text: str) -> int:
    """Width of the text in terminal cells (CJK/emoji take two)."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if limit <= 0 or display_width(text) <= limit:
        return text
    out = ""
    for ch in text:
        if display_width(out) + display_width(ch) > limit - 1:
            break
        out += ch
    return out + "…"


def read_csv(path: Path, delimiter: str | None, encoding: str) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding=encoding) as fh:
        sample = fh.read(64 * 1024)
        fh.seek(0)
        if delimiter is None:
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        rows = list(csv.reader(fh, delimiter=delimiter))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def letters_to_index(token: str) -> int | None:
    """A -> 0, B -> 1, ... Z -> 25, AA -> 26. None if not a letter reference."""
    if not token.isalpha() or not token.isascii() or len(token) > 2:
        return None  # longer words are column names, not spreadsheet letters
    number = 0
    for ch in token.upper():
        number = number * 26 + (ord(ch) - ord("A") + 1)
    return number - 1


def resolve_column(header: list[str], token: str) -> int:
    """A single column reference: exact name, 1-based number, or spreadsheet letter."""
    if token in header:
        return header.index(token)
    if token.isdigit():
        index = int(token) - 1
    else:
        index = letters_to_index(token)
        if index is None:
            raise SystemExit(f"unknown column: {token}")
    if not 0 <= index < len(header):
        raise SystemExit(f"column out of range (file has {len(header)}): {token}")
    return index


def pick_columns(header: list[str], wanted: list[str]) -> list[int]:
    """Resolve a --columns spec: names, 1-based numbers, letters, and A-D / 2-5 ranges."""
    indexes = []
    for token in wanted:
        if token not in header and "-" in token[1:]:
            start, _, end = token.partition("-")
            first, last = resolve_column(header, start), resolve_column(header, end)
            step = 1 if last >= first else -1
            indexes.extend(range(first, last + step, step))
        else:
            indexes.append(resolve_column(header, token))
    return indexes


def render_table(header: list[str], rows: list[list[str]], max_width: int) -> str:
    cells = [[shorten(c, max_width) for c in row] for row in rows]
    widths = [display_width(h) for h in header]
    for row in cells:
        for i, cell in enumerate(row[: len(widths)]):
            widths[i] = max(widths[i], display_width(cell))

    lines = [" | ".join(pad(h, w) for h, w in zip(header, widths))]
    lines.append("-+-".join("-" * w for w in widths))
    for row in cells:
        row = row + [""] * (len(widths) - len(row))
        lines.append(" | ".join(pad(c, w) for c, w in zip(row, widths)).rstrip())
    return "\n".join(lines)


def render_records(header: list[str], rows: list[list[str]], max_width: int) -> str:
    label = max((display_width(h) for h in header), default=0)
    blocks = []
    for number, row in enumerate(rows, start=1):
        block = [f"=== record {number} ==="]
        for i, name in enumerate(header):
            value = shorten(row[i], max_width) if i < len(row) else ""
            block.append(f"{pad(name, label)} : {value}")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="CSV file to convert")
    parser.add_argument("-o", "--output", type=Path, help="txt file to write (default: stdout)")
    parser.add_argument(
        "-f",
        "--format",
        choices=("table", "records"),
        default="table",
        help="table: aligned columns; records: one field per line (default: table)",
    )
    parser.add_argument(
        "-c",
        "--columns",
        help="columns to keep, comma separated: names, 1-based numbers, spreadsheet "
        "letters, or ranges (e.g. 'author,3,F,B-D'). Order is preserved",
    )
    parser.add_argument(
        "-w",
        "--max-width",
        type=int,
        default=40,
        help="truncate cells wider than this, 0 disables (default: 40)",
    )
    parser.add_argument("-d", "--delimiter", help="CSV delimiter (default: autodetect)")
    parser.add_argument("-e", "--encoding", default="utf-8-sig", help="default: utf-8-sig")
    parser.add_argument("-n", "--limit", type=int, help="convert only the first N data rows")
    args = parser.parse_args(argv)

    if not args.csv_path.is_file():
        raise SystemExit(f"no such file: {args.csv_path}")

    header, rows = read_csv(args.csv_path, args.delimiter, args.encoding)
    if not header:
        raise SystemExit(f"{args.csv_path} is empty")

    if args.columns:
        keep = pick_columns(header, [c.strip() for c in args.columns.split(",") if c.strip()])
        header = [header[i] for i in keep]
        rows = [[row[i] if i < len(row) else "" for i in keep] for row in rows]

    if args.limit is not None:
        rows = rows[: args.limit]

    render = render_table if args.format == "table" else render_records
    text = render(header, rows, args.max_width)
    title = f"{args.csv_path.name} — {len(rows)} rows, {len(header)} columns"
    text = f"{title}\n{'=' * display_width(title)}\n\n{text}\n"

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
