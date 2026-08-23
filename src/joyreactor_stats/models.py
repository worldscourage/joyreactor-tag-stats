"""The two records this project produces: a post and an author summary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Post:
    """A single post in a tag line, as far as we care about it."""

    id: int
    url: str
    author: str
    title: str
    score: float
    """The rating users voted the post to: positive for likes, negative for dislikes."""
    score_general: float
    """The site's secondary "general" rating, kept because it is free to collect."""
    comments: int
    created_at: datetime
    nsfw: bool
    banned: bool

    @property
    def display_title(self) -> str:
        """Something printable even for image-only posts, which carry no text."""
        return self.title or "(no text — image or video post)"


@dataclass(frozen=True, slots=True)
class AuthorSummary:
    """Aggregated stats for one author over a set of posts."""

    author: str
    posts: int
    score_min: float
    score_max: float
    score_sum: float
    score_avg: float
    comments_sum: int
    first_post_at: datetime
    last_post_at: datetime
