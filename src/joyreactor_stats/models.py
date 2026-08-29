"""The records this project produces: posts, comment highlights, author summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .rating import stars_for_rating


@dataclass(frozen=True, slots=True)
class Comment:
    """One comment, reduced to what the per-post highlights need."""

    id: int
    author: str
    score: float
    parent_id: int | None
    """The comment this one replies to; ``None`` for a top-level comment."""


@dataclass(frozen=True, slots=True)
class CommentStats:
    """The three highlights of a post's comment thread."""

    best_author: str
    best_score: float
    worst_author: str
    worst_score: float
    most_replied_author: str
    most_replied_direct: int
    """Replies made straight to that comment."""
    most_replied_total: int
    """Replies in its whole subtree, however deeply nested."""


@dataclass(frozen=True, slots=True)
class Post:
    """A single post in a tag line, as far as we care about it."""

    id: int
    url: str
    author: str
    author_rating: float
    """The author's site-wide rating at the time we read the post."""
    title: str
    score: float
    """The rating users voted the post to: positive for likes, negative for dislikes."""
    score_general: float
    """The site's secondary "general" rating, kept because it is free to collect."""
    comments: int
    created_at: datetime
    nsfw: bool
    banned: bool
    tags: tuple[str, ...] = ()
    """The post's tags, in the order the site lists them."""
    comment_stats: CommentStats | None = None
    """Filled in only when comment collection is enabled and the post has comments."""

    @property
    def author_stars(self) -> int:
        """The author's rating expressed as the star count the site shows."""
        return stars_for_rating(self.author_rating)

    @property
    def display_title(self) -> str:
        """Something printable even for image-only posts, which carry no text."""
        return self.title or "(no text — image or video post)"


@dataclass(frozen=True, slots=True)
class AuthorSummary:
    """Aggregated stats for one author over a set of posts."""

    author: str
    author_rating: float
    """Their site-wide rating, taken from their most recent post in the window."""
    posts: int
    score_min: float
    score_max: float
    score_sum: float
    score_avg: float
    score_positive_sum: float
    """Scores of their upvoted posts only; ``0.0`` when they have none."""
    score_negative_sum: float
    """Scores of their downvoted posts only — negative, or ``0.0`` when none."""
    comments_sum: int
    first_post_at: datetime
    last_post_at: datetime

    @property
    def author_stars(self) -> int:
        """The rating expressed as the star count the site shows."""
        return stars_for_rating(self.author_rating)
