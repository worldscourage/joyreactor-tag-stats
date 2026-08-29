"""Small builders shared by the tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from joyreactor_stats.config import SITE_TIMEZONE
from joyreactor_stats.models import Comment, Post


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


def make_comment(
    comment_id: int,
    author: str = "someone",
    score: float = 0.0,
    *,
    post_id: int = 1,
    text: str = "",
    author_rating: float = 0.0,
    direct_replies: int = 0,
    total_replies: int = 0,
    parent_id: int | None = None,
) -> Comment:
    """A Comment already carrying its reply counts, as the scraper hands them over."""
    return Comment(
        id=comment_id,
        author=author,
        score=score,
        parent_id=parent_id,
        post_id=post_id,
        text=text or f"comment {comment_id}",
        author_rating=author_rating,
        direct_replies=direct_replies,
        total_replies=total_replies,
    )
