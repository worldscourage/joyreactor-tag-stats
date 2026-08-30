"""Writing results out: CSV files, JSON, and plain-text tables."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .models import AuthorSummary, Comment, Post

#: How many stars the site fits on one row before starting another; we use it
#: only to decide when spelling the stars out stops being readable.
STARS_PER_ROW = 10

POST_COLUMNS = (
    "id",
    "created_at",
    "author",
    "author_rating",
    "author_stars",
    "score",
    "score_general",
    "comments",
    "title",
    "url",
    "nsfw",
    "banned",
    # Comment-thread highlights; empty when comments were not collected or the
    # post has no comments.
    "best_comment_author",
    "best_comment_score",
    "worst_comment_author",
    "worst_comment_score",
    "most_replied_comment_author",
    "most_replied_direct_replies",
    "most_replied_total_replies",
)

AUTHOR_COLUMNS = (
    "author",
    "author_rating",
    "author_stars",
    "posts",
    "score_min",
    "score_max",
    "score_sum",
    "score_avg",
    "score_positive_sum",
    "score_negative_sum",
    "comments_sum",
    "first_post_at",
    "last_post_at",
)


def format_site_share(share: dict) -> str:
    """The tag's slice of the site, for the console."""
    if share.get("percent") is None:
        return "Share of the site: nothing was posted in the period"

    line = (
        f"Share of the site: {share['tag_posts']} of {share['site_posts']} posts "
        f"({share['percent']:.2f}%)"
    )
    if not share.get("complete"):
        line += (
            f"\n  (over {share['covered_from'][:16]} … {share['covered_to'][:16]} only — "
            "as far as the site feed reaches)"
        )
    return line


def format_side_total(value: float) -> str:
    """A one-sided total, where zero means "nothing on this side at all".

    Signing that zero would read as a tiny plus or minus rather than as an
    absence, so it is the one value here printed without one.
    """
    return "0.00" if value == 0 else f"{value:+.2f}"


def format_stars(stars: int) -> str:
    """Stars as the site draws them, folded to ``★×N`` once a row is full."""
    if stars <= STARS_PER_ROW:
        return "★" * stars
    return f"★×{stars}"


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
    comments: Sequence[Comment] = (),
) -> None:
    """One self-describing file with the run parameters and every result set.

    The comments are included when they were collected, which is what lets
    ``joy-champions`` re-run the champions pass against this file alone.
    """
    from .champions import comment_rows  # Imported here to avoid a cycle.

    document = {
        "meta": meta,
        "posts": [_post_row(post) for post in posts],
        "authors": [_author_row(item) for item in authors],
        "comments": comment_rows(comments),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def format_posts_table(posts: Sequence[Post], limit: int | None = None) -> str:
    rows = list(posts if limit is None else posts[:limit])
    table = _render_table(
        headers=("Date", "Author", "Stars", "Score", "Comments", "Title"),
        rows=[
            (
                post.created_at.strftime("%Y-%m-%d %H:%M"),
                post.author,
                format_stars(post.author_stars),
                f"{post.score:+.2f}",
                str(post.comments),
                post.display_title,
            )
            for post in rows
        ],
        aligns=("<", "<", "<", ">", ">", "<"),
        max_widths=(16, 24, 12, 9, 8, 60),
    )
    if limit is not None and len(posts) > limit:
        table += f"\n… and {len(posts) - limit} more posts (see the CSV/JSON output)"
    return table


def format_authors_table(summaries: Sequence[AuthorSummary]) -> str:
    return _render_table(
        headers=(
            "Author",
            "Stars",
            "Rating",
            "Posts",
            "Min",
            "Max",
            "Sum",
            "Avg",
            "Plus",
            "Minus",
            "Comments",
        ),
        rows=[
            (
                item.author,
                format_stars(item.author_stars),
                f"{item.author_rating:.0f}",
                str(item.posts),
                f"{item.score_min:+.2f}",
                f"{item.score_max:+.2f}",
                f"{item.score_sum:+.2f}",
                f"{item.score_avg:+.2f}",
                format_side_total(item.score_positive_sum),
                format_side_total(item.score_negative_sum),
                str(item.comments_sum),
            )
            for item in summaries
        ],
        aligns=("<", "<", ">", ">", ">", ">", ">", ">", ">", ">", ">"),
        max_widths=(28, 12, 9, 6, 10, 10, 12, 10, 12, 12, 9),
    )


def format_comment_highlights(posts: Sequence[Post], limit: int | None = None) -> str:
    """Per-post best / worst / most-answered comment, for the console."""
    rows = [post for post in posts if post.comment_stats is not None]
    if not rows:
        return "(no comment data — the posts have no comments, or --no-comment-stats was used)"

    shown = rows if limit is None else rows[:limit]
    table = _render_table(
        headers=(
            "Post",
            "Best comment by",
            "Score",
            "Worst comment by",
            "Score",
            "Most answered by",
            "Direct",
            "All",
        ),
        rows=[
            (
                str(post.id),
                post.comment_stats.best_author,
                f"{post.comment_stats.best_score:+.2f}",
                post.comment_stats.worst_author,
                f"{post.comment_stats.worst_score:+.2f}",
                post.comment_stats.most_replied_author,
                str(post.comment_stats.most_replied_direct),
                str(post.comment_stats.most_replied_total),
            )
            for post in shown
        ],
        aligns=("<", "<", ">", "<", ">", "<", ">", ">"),
        max_widths=(9, 20, 8, 20, 8, 20, 7, 5),
    )
    if limit is not None and len(rows) > limit:
        table += f"\n… and {len(rows) - limit} more posts with comments"
    return table


def _post_row(post: Post) -> dict[str, Any]:
    stats = post.comment_stats
    return {
        "id": post.id,
        "created_at": post.created_at.isoformat(),
        "author": post.author,
        "author_rating": round(post.author_rating, 2),
        "author_stars": post.author_stars,
        "score": round(post.score, 3),
        "score_general": round(post.score_general, 3),
        "comments": post.comments,
        "title": post.title,
        "url": post.url,
        "nsfw": post.nsfw,
        "banned": post.banned,
        "best_comment_author": stats.best_author if stats else "",
        "best_comment_score": round(stats.best_score, 3) if stats else "",
        "worst_comment_author": stats.worst_author if stats else "",
        "worst_comment_score": round(stats.worst_score, 3) if stats else "",
        "most_replied_comment_author": stats.most_replied_author if stats else "",
        "most_replied_direct_replies": stats.most_replied_direct if stats else "",
        "most_replied_total_replies": stats.most_replied_total if stats else "",
    }


def _author_row(item: AuthorSummary) -> dict[str, Any]:
    return {
        "author": item.author,
        "author_rating": round(item.author_rating, 2),
        "author_stars": item.author_stars,
        "posts": item.posts,
        "score_min": round(item.score_min, 3),
        "score_max": round(item.score_max, 3),
        "score_sum": round(item.score_sum, 3),
        "score_avg": round(item.score_avg, 3),
        "score_positive_sum": round(item.score_positive_sum, 3),
        "score_negative_sum": round(item.score_negative_sum, 3),
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
