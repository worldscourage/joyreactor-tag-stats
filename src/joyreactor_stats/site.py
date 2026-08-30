"""Counting how many posts the whole site published in a period.

This is what turns "34 posts" into "34 posts, which was 6% of everything posted
that day". The site has no endpoint that simply answers it, so the count comes
from walking the site-wide feed newest-first and stopping at the start of the
window — the same shape as a tag line, one request per ten posts.

The feed is bounded at both ends. It hands out at most :data:`FEED_LIMIT` posts
and then returns nothing, which at the site's usual pace is a bit under two
days; and it is an index that lags live by hours, so its newest post can be well
behind the end of the window. Either way the walk reports the stretch it could
actually see, and the share is worked out over that stretch alone — comparing a
full tag selection against a partial site count would overstate the tag every
time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from .client import GraphQLClient
from .models import Post

logger = logging.getLogger(__name__)

#: The site-wide feed stops here; offsets past it come back empty.
FEED_LIMIT = 1000

#: Posts newest-first across every tag. ``query: ""`` matches everything, and
#: unlike the tag line these pages do not overlap.
SITE_POSTS_QUERY = """
query SitePosts($offset: Int!) {
  search(query: "", sortByDate: true) {
    postPager {
      count
      posts(offset: $offset) {
        id
        createdAt
      }
    }
  }
}
"""


@dataclass(frozen=True, slots=True)
class SiteCoverage:
    """How many posts the site published in the part of the window we could see."""

    posts: int
    covered_from: datetime
    """The oldest moment the feed reached; the window start when complete."""
    covered_to: datetime
    """The newest moment the feed knows about; the window end when complete.

    The site's search index runs behind live, so this is routinely earlier than
    the end of the window even for a period that finished long ago.
    """
    complete: bool
    """False when the feed could not cover the whole window."""

    def share_of(self, tag_posts: int) -> float | None:
        """The tag's percentage of the site, or ``None`` when nothing was posted."""
        if self.posts <= 0:
            return None
        return 100.0 * tag_posts / self.posts


def count_site_posts(
    client: GraphQLClient, start: datetime, end: datetime
) -> SiteCoverage:
    """Count every post the site published within ``[start, end]``.

    Costs one request per ten posts, so a day of the site is around 50 of them.
    """
    if start > end:
        raise ValueError("start must not be later than end")

    counted = 0
    offset = 0
    oldest_seen = end
    newest_seen: datetime | None = None
    reached_start = False

    while offset < FEED_LIMIT:
        rows = _fetch(client, offset)
        if not rows:
            break  # The feed is exhausted, whether or not we reached `start`.
        offset += len(rows)

        for row in rows:
            try:
                created_at = datetime.fromisoformat(row["createdAt"])
            except (KeyError, TypeError, ValueError):
                continue  # One unreadable row must not end the count.
            if newest_seen is None:
                # The very first row is the newest the index holds, which is
                # how far towards `end` this answer can reach.
                newest_seen = created_at
            if created_at > end:
                continue
            if created_at < start:
                reached_start = True
                break
            oldest_seen = created_at
            counted += 1
        if reached_start:
            break

    covered_to = min(newest_seen or end, end)
    covered_from = start if reached_start else oldest_seen
    complete = reached_start and covered_to >= end

    if not complete:
        logger.warning(
            "The site-wide feed covers only %s … %s, so the share is worked out "
            "over that stretch rather than the whole period.",
            covered_from.isoformat(timespec="minutes"),
            covered_to.isoformat(timespec="minutes"),
        )
    return SiteCoverage(counted, covered_from, covered_to, complete=complete)


def _fetch(client: GraphQLClient, offset: int) -> list[dict]:
    data = client.execute(SITE_POSTS_QUERY, {"offset": offset})
    pager = ((data.get("search") or {}).get("postPager")) or {}
    return pager.get("posts") or []


def tag_posts_between(posts: list[Post], since: datetime, until: datetime) -> int:
    """How many of ``posts`` fall in the stretch the site count actually covers."""
    return sum(1 for post in posts if since <= post.created_at <= until)
