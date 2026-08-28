"""Aggregating posts into per-author summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from .models import AuthorSummary, Post

#: Fields the CLI accepts for ``--sort-authors-by``.
AUTHOR_SORT_KEYS = (
    "score_sum",
    "score_max",
    "author_rating",
    "score_min",
    "score_avg",
    "posts",
    "comments_sum",
    "author",
)


def summarize_by_author(
    posts: Iterable[Post], *, sort_by: str = "score_sum"
) -> list[AuthorSummary]:
    """Group ``posts`` per author and compute min/max/sum/count of their scores.

    Sorted by ``sort_by`` descending, except for ``author`` which sorts
    alphabetically because that is the only order a name makes sense in.
    """
    if sort_by not in AUTHOR_SORT_KEYS:
        raise ValueError(
            f"Unknown sort key {sort_by!r}; expected one of {', '.join(AUTHOR_SORT_KEYS)}"
        )

    grouped: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        grouped[post.author].append(post)

    summaries = [_summarize_one(author, group) for author, group in grouped.items()]
    if sort_by == "author":
        summaries.sort(key=lambda summary: summary.author.casefold())
    else:
        summaries.sort(key=lambda summary: getattr(summary, sort_by), reverse=True)
    return summaries


def _summarize_one(author: str, posts: Sequence[Post]) -> AuthorSummary:
    scores = [post.score for post in posts]
    dates = [post.created_at for post in posts]
    total = sum(scores)
    # An author's rating changes over time, so the freshest post we saw carries
    # the closest thing to their rating right now.
    newest = max(posts, key=lambda post: post.created_at)
    return AuthorSummary(
        author=author,
        author_rating=newest.author_rating,
        posts=len(posts),
        score_min=min(scores),
        score_max=max(scores),
        score_sum=total,
        score_avg=total / len(posts),
        comments_sum=sum(post.comments for post in posts),
        first_post_at=min(dates),
        last_post_at=max(dates),
    )


def overall_totals(posts: Sequence[Post]) -> dict[str, float | int]:
    """A few headline numbers for the run, handy for the report header."""
    if not posts:
        return {"posts": 0, "authors": 0, "score_sum": 0.0, "comments_sum": 0}
    return {
        "posts": len(posts),
        "authors": len({post.author for post in posts}),
        "score_sum": sum(post.score for post in posts),
        "comments_sum": sum(post.comments for post in posts),
    }
