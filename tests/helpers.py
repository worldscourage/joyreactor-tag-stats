"""Small builders shared by the tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from joyreactor_stats.config import SITE_TIMEZONE
from joyreactor_stats.models import Post


def make_post(
    post_id: int,
    author: str = "someone",
    score: float = 0.0,
    *,
    comments: int = 0,
    minutes_ago: int = 0,
    title: str | None = None,
    author_rating: float = 0.0,
    tags: tuple[str, ...] = (),
) -> Post:
    """A Post with sensible defaults, so tests only state what they care about."""
    created = datetime(2025, 8, 31, 12, 0, tzinfo=SITE_TIMEZONE) - timedelta(minutes=minutes_ago)
    return Post(
        id=post_id,
        url=f"https://joyreactor.cc/post/{post_id}",
        author=author,
        author_rating=author_rating,
        title=f"post {post_id}" if title is None else title,
        score=score,
        score_general=0.0,
        comments=comments,
        created_at=created,
        nsfw=False,
        banned=False,
        tags=tags,
    )
