"""Walking a tag line and turning API rows into :class:`Post` records."""

from __future__ import annotations

import base64
import binascii
import logging
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlparse

from . import config
from .client import GraphQLClient, JoyreactorError
from .comments import fetch_comment_stats
from .models import Post
from .text import derive_title

logger = logging.getLogger(__name__)

#: One request per page of the tag line. ``postPager.posts(offset:)`` returns
#: posts newest-first, which is what lets us stop early on a date range.
TAG_POSTS_QUERY = """
query TagPosts($tag: String!, $lineType: PostLineType!, $offset: Int!) {
  tag(name: $tag) {
    id
    name
    postPager(type: $lineType) {
      count
      posts(offset: $offset) {
        id
        createdAt
        rating
        ratingGeneral
        commentsCount
        text
        nsfw
        banned
        user {
          username
        }
      }
    }
  }
}
"""


class TagScraper:
    """Reads posts of a single tag, newest first, with an optional date window."""

    def __init__(
        self,
        client: GraphQLClient,
        *,
        max_requests: int | None = None,
        title_length: int = 120,
        with_comment_stats: bool = False,
    ) -> None:
        self._client = client
        self._max_requests = max_requests
        self._title_length = title_length
        self._with_comment_stats = with_comment_stats
        self.total_posts_in_tag: int | None = None
        """Post count the API reports for the whole tag line (not just our window)."""

    def iter_posts(self, tag: str, line_type: str = "ALL") -> Iterator[Post]:
        """Yield every post of ``tag``, newest first.

        The API pages by item offset and returns overlapping batches, so we
        de-duplicate by post id and advance by the batch size. An empty batch,
        or a batch that adds nothing new, means we reached the end.
        """
        offset = 0
        seen: set[int] = set()

        while True:
            if self._out_of_budget():
                return

            batch = self._fetch_batch(tag, line_type, offset)
            if not batch:
                return

            fresh = [post for post in batch if post.id not in seen]
            if not fresh:
                # Server keeps handing us the same window; nothing left to read.
                return

            seen.update(post.id for post in fresh)
            yield from fresh
            offset += len(batch)

    def fetch_range(
        self,
        tag: str,
        start: datetime,
        end: datetime,
        line_type: str = "ALL",
    ) -> list[Post]:
        """Collect the posts of ``tag`` created within ``[start, end]``.

        Because the line is ordered newest first, we can stop as soon as we walk
        past ``start`` instead of reading the whole tag.
        """
        if start > end:
            raise ValueError("start must not be later than end")

        collected: list[Post] = []
        for post in self.iter_posts(tag, line_type):
            if post.created_at > end:
                continue  # Still newer than the window: keep walking back.
            if post.created_at < start:
                break  # Everything further back is older than the window.
            collected.append(post)

        if self._with_comment_stats:
            collected = self.attach_comment_stats(collected)
        return collected

    def attach_comment_stats(self, posts: Sequence[Post]) -> list[Post]:
        """Return ``posts`` with their comment highlights filled in.

        Costs one request per post that has comments, so it is opt-in. A post
        whose thread cannot be read keeps its other data and is logged.
        """
        with_comments = [post for post in posts if post.comments]
        logger.info(
            "Reading comment threads for %d of %d posts", len(with_comments), len(posts)
        )

        enriched = []
        for number, post in enumerate(posts, start=1):
            if self._out_of_budget():
                enriched.extend(posts[number - 1 :])  # Keep the rest, unenriched.
                break
            if not post.comments:
                enriched.append(post)  # Nothing to fetch, nothing to say.
                continue
            try:
                stats = fetch_comment_stats(self._client, encode_global_id("Post", post.id))
            except JoyreactorError as error:
                logger.warning("Comments unavailable for post %d: %s", post.id, error)
                enriched.append(post)
                continue
            enriched.append(replace(post, comment_stats=stats))
            if number % 25 == 0:
                logger.info("… %d/%d posts processed", number, len(posts))
        return enriched

    def _out_of_budget(self) -> bool:
        """True once we have spent the caller's request allowance."""
        if self._max_requests is None:
            return False
        if self._client.requests_made < self._max_requests:
            return False
        logger.warning(
            "Stopping: reached the %d request cap; results are incomplete",
            self._max_requests,
        )
        return True

    def _fetch_batch(self, tag: str, line_type: str, offset: int) -> list[Post]:
        data = self._client.execute(
            TAG_POSTS_QUERY,
            {"tag": tag, "lineType": line_type, "offset": offset},
        )
        tag_node = data.get("tag")
        if not tag_node:
            raise JoyreactorError(f"Tag not found: {tag!r}")

        pager = tag_node.get("postPager") or {}
        if self.total_posts_in_tag is None:
            self.total_posts_in_tag = pager.get("count")

        rows = pager.get("posts") or []
        posts = []
        for row in rows:
            post = self._parse_post(row)
            if post is not None:
                posts.append(post)
        return posts

    def _parse_post(self, row: dict[str, Any]) -> Post | None:
        """Convert one API row into a :class:`Post`, skipping unusable rows."""
        try:
            post_id = decode_global_id(row["id"])
            created_at = datetime.fromisoformat(row["createdAt"])
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Skipping a post we could not parse: %s", error)
            return None

        user = row.get("user") or {}
        return Post(
            id=post_id,
            url=f"{config.SITE_URL}/post/{post_id}",
            author=user.get("username") or "(deleted user)",
            title=derive_title(row.get("text"), self._title_length),
            score=float(row.get("rating") or 0.0),
            score_general=float(row.get("ratingGeneral") or 0.0),
            comments=int(row.get("commentsCount") or 0),
            created_at=created_at,
            nsfw=bool(row.get("nsfw")),
            banned=bool(row.get("banned")),
        )


def decode_global_id(global_id: str) -> int:
    """Turn a Relay id such as ``UG9zdDo2MzA5OTE0`` into ``6309914``."""
    try:
        decoded = base64.b64decode(global_id, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ValueError(f"Not a Relay global id: {global_id!r}") from error

    _, _, numeric = decoded.partition(":")
    if not numeric.isdigit():
        raise ValueError(f"Unexpected global id payload: {decoded!r}")
    return int(numeric)


def encode_global_id(kind: str, numeric_id: int) -> str:
    """The inverse of :func:`decode_global_id`: ``("Post", 6309914)`` → ``UG9zdDo2MzA5OTE0``."""
    return base64.b64encode(f"{kind}:{numeric_id}".encode()).decode()


def parse_tag_url(url: str) -> tuple[str, str]:
    """Extract ``(tag, line_type)`` from a tag URL as copied from the browser.

    >>> parse_tag_url("https://joyreactor.cc/tag/anon/all")
    ('anon', 'ALL')
    """
    path = urlparse(url).path.strip("/")
    parts = [unquote(part) for part in path.split("/") if part]
    if not parts or parts[0] != "tag" or len(parts) < 2:
        raise ValueError(f"Not a joyreactor tag URL: {url!r}")

    tag = parts[1]
    line_type = "ALL"
    for part in parts[2:]:
        candidate = config.LINE_TYPES.get(part.lower())
        if candidate:
            line_type = candidate
    return tag, line_type
