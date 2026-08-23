"""Writing results out: CSV files, JSON, and plain-text tables."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .models import AuthorSummary, Post

POST_COLUMNS = (
    "id",
    "created_at",
    "author",
    "score",
    "score_general",
    "comments",
    "title",
    "url",
    "nsfw",
    "banned",
)

AUTHOR_COLUMNS = (
    "author",
    "posts",
    "score_min",
    "score_max",
    "score_sum",
    "score_avg",
    "comments_sum",
    "first_post_at",
    "last_post_at",
)


def write_posts_csv(posts: Sequence[Post], path: Path) -> None:
    _write_csv(path, POST_COLUMNS, (_post_row(post) for post in posts))


def write_authors_csv(summaries: Sequence[AuthorSummary], path: Path) -> None:
    _write_csv(path, AUTHOR_COLUMNS, (_author_row(item) for item in summaries))


def write_json(
    path: Path,
    *,
    meta: dict[str, Any],
    posts: Sequence[Post],
    authors: Sequence[AuthorSummary],
) -> None:
    """One self-describing file with the run parameters and both result sets."""
    document = {
        "meta": meta,
        "posts": [_post_row(post) for post in posts],
        "authors": [_author_row(item) for item in authors],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def format_posts_table(posts: Sequence[Post], limit: int | None = None) -> str:
    rows = list(posts if limit is None else posts[:limit])
    table = _render_table(
        headers=("Date", "Author", "Score", "Comments", "Title"),
        rows=[
            (
                post.created_at.strftime("%Y-%m-%d %H:%M"),
                post.author,
                f"{post.score:+.2f}",
                str(post.comments),
                post.display_title,
            )
            for post in rows
        ],
        aligns=("<", "<", ">", ">", "<"),
        max_widths=(16, 24, 9, 8, 60),
    )
    if limit is not None and len(posts) > limit:
        table += f"\n… and {len(posts) - limit} more posts (see the CSV/JSON output)"
    return table


def format_authors_table(summaries: Sequence[AuthorSummary]) -> str:
    return _render_table(
        headers=("Author", "Posts", "Min", "Max", "Sum", "Avg", "Comments"),
        rows=[
            (
                item.author,
                str(item.posts),
                f"{item.score_min:+.2f}",
                f"{item.score_max:+.2f}",
                f"{item.score_sum:+.2f}",
                f"{item.score_avg:+.2f}",
                str(item.comments_sum),
            )
            for item in summaries
        ],
        aligns=("<", ">", ">", ">", ">", ">", ">"),
        max_widths=(28, 6, 10, 10, 12, 10, 9),
    )


def _post_row(post: Post) -> dict[str, Any]:
    return {
        "id": post.id,
        "created_at": post.created_at.isoformat(),
        "author": post.author,
        "score": round(post.score, 3),
        "score_general": round(post.score_general, 3),
        "comments": post.comments,
        "title": post.title,
        "url": post.url,
        "nsfw": post.nsfw,
        "banned": post.banned,
    }


def _author_row(item: AuthorSummary) -> dict[str, Any]:
    return {
        "author": item.author,
        "posts": item.posts,
        "score_min": round(item.score_min, 3),
        "score_max": round(item.score_max, 3),
        "score_sum": round(item.score_sum, 3),
        "score_avg": round(item.score_avg, 3),
        "comments_sum": item.comments_sum,
        "first_post_at": item.first_post_at.isoformat(),
        "last_post_at": item.last_post_at.isoformat(),
    }


def _write_csv(path: Path, columns: Sequence[str], rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so that Excel on Windows opens Cyrillic names correctly.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


def _render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    aligns: Sequence[str],
    max_widths: Sequence[int],
) -> str:
    if not rows:
        return "(nothing to show)"

    cells = [
        [_clip(value, width) for value, width in zip(row, max_widths, strict=True)]
        for row in rows
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in cells))
        for index, header in enumerate(headers)
    ]

    def line(values: Sequence[str]) -> str:
        return "  ".join(
            f"{value:{align}{width}}"
            for value, align, width in zip(values, aligns, widths, strict=True)
        ).rstrip()

    separator = "  ".join("-" * width for width in widths)
    return "\n".join([line(headers), separator, *(line(row) for row in cells)])


def _clip(value: str, width: int) -> str:
    return value if len(value) <= width else value[: width - 1] + "…"
