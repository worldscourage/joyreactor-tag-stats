"""The records this project produces: posts, comment highlights, author summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import SITE_URL
from .rating import stars_for_rating


@dataclass(frozen=True, slots=True)
class Comment:
    """One comment, reduced to what the per-post highlights need."""

    id: int
    author: str
    score: float
    parent_id: int | None
    """The comment this one replies to; ``None`` for a top-level comment."""
    post_id: int = 0
    """The post it was written under, which is what makes a link to it."""
    text: str = ""
    """A short plain-text excerpt, standing in for the title a comment lacks."""
    author_rating: float = 0.0
    direct_replies: int = 0
    total_replies: int = 0
    """Both counts are filled in once the whole thread is known."""

    @property
    def url(self) -> str:
        """Permalink, in the ``/post/123#comment456`` form the site itself uses."""
        return f"{SITE_URL}/post/{self.post_id}#comment{self.id}"

    @property
    def author_stars(self) -> int:
        return stars_for_rating(self.author_rating)


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


@dataclass(frozen=True, slots=True)
class Champion:
    """One line of a champions chapter: a post or a comment that stood out.

    Deliberately flat and already resolved — a renderer should only have to
    format these fields, never go looking for the record behind them, which is
    what lets the same entry print in any language.
    """

    kind: str
    """``"post"`` or ``"comment"``; decides how a renderer labels the link."""
    title: str
    url: str
    score: float
    """The instance's own rating, not its author's."""
    author: str
    author_rating: float
    direct_replies: int | None = None
    total_replies: int | None = None
    """Only set for entries chosen by how much they were answered."""
    comments: int | None = None
    """Only set where the comment count is the reason the entry is here."""
    posts: int | None = None
    score_abs_sum: float | None = None
    score_negative_sum: float | None = None
    """Set on author entries, where the whole body of work is the subject."""
    chapters: tuple[str, ...] | None = None
    """Chapter keys an epic hero turned up in; titled by whoever renders them."""

    @property
    def author_stars(self) -> int:
        return stars_for_rating(self.author_rating)


@dataclass(frozen=True, slots=True)
class Chapter:
    """A titled group of champions.

    ``key`` is the stable name used in the JSON and to look a title up per
    language, so adding a language never means touching the building code.
    """

    key: str
    entries: tuple[Champion, ...]
    empty_reason: str | None = None
    """Why a chapter came out empty, when that is worth saying out loud."""
