"""Per-post comment highlights: the best, the worst, and the most-answered comment.

A post's whole comment tree arrives in a single request, so the work here is
mostly shaping: build the parent → children map, then read three answers out of
it. Everything below the fetch is pure, which keeps it easy to test.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

from .client import GraphQLClient
from .models import Comment, CommentStats
from .text import derive_title

logger = logging.getLogger(__name__)

#: Comments have no title, so a short excerpt of the text stands in for one.
COMMENT_EXCERPT_LENGTH = 100

#: ``parent`` is an interface: a comment answers either the post or another
#: comment, so the id is only available behind an inline fragment.
POST_COMMENTS_QUERY = """
query PostComments($id: ID!) {
  node(id: $id) {
    ... on Post {
      id
      comments {
        id
        rating
        banned
        text
        user {
          username
          rating
        }
        parent {
          __typename
          ... on Comment {
            id
          }
        }
      }
    }
  }
}
"""


def analyze_comments(
    comments: Sequence[Comment],
) -> tuple[CommentStats | None, list[Comment]]:
    """Reduce a thread to its highlights *and* hand back the comments enriched.

    The reply counts are wanted twice over — once for this post's highlights,
    once for the champions pass across every post — so they are counted here
    only, and written onto the comments themselves.
    """
    if not comments:
        return None, []

    direct, total = count_replies(comments)
    counted = [
        replace(
            comment,
            direct_replies=direct[comment.id],
            total_replies=total[comment.id],
        )
        for comment in comments
    ]

    best = max(counted, key=lambda comment: comment.score)
    worst = min(counted, key=lambda comment: comment.score)
    most_replied = max(
        counted,
        key=lambda comment: (comment.total_replies, comment.direct_replies),
    )

    stats = CommentStats(
        best_author=best.author,
        best_score=best.score,
        worst_author=worst.author,
        worst_score=worst.score,
        most_replied_author=most_replied.author,
        most_replied_direct=most_replied.direct_replies,
        most_replied_total=most_replied.total_replies,
    )
    return stats, counted


def summarize_comments(comments: Sequence[Comment]) -> CommentStats | None:
    """A post's three comment highlights, for callers that want nothing else.

    Returns ``None`` for a post with no comments, which is a normal state and
    not an error. Ties are broken in favour of the earlier comment, so repeated
    runs over the same post always agree.
    """
    return analyze_comments(comments)[0]


def count_replies(
    comments: Sequence[Comment],
) -> tuple[dict[int, int], dict[int, int]]:
    """Count direct and recursive replies for every comment.

    Returns ``(direct, total)`` keyed by comment id, where ``total`` counts the
    entire subtree below a comment — replies, replies to those, and so on.
    """
    known_ids = {comment.id for comment in comments}
    children: dict[int, list[int]] = defaultdict(list)
    for comment in comments:
        # A parent outside the fetched set (deleted, or a partial thread) makes
        # this comment a root rather than losing it.
        if comment.parent_id is not None and comment.parent_id in known_ids:
            children[comment.parent_id].append(comment.id)

    direct = {comment.id: len(children.get(comment.id, ())) for comment in comments}
    total = dict.fromkeys(known_ids, 0)

    # Walk parents-before-children, then accumulate in reverse so every child's
    # subtree is already known when we reach its parent. An explicit stack keeps
    # deep threads from hitting the recursion limit.
    for comment_id in reversed(_preorder(comments, children, known_ids)):
        total[comment_id] = sum(
            total[child] + 1 for child in children.get(comment_id, ())
        )
    return direct, total


def _preorder(
    comments: Sequence[Comment],
    children: dict[int, list[int]],
    known_ids: set[int],
) -> list[int]:
    """Comment ids ordered so that a parent always precedes its children."""
    roots = [
        comment.id
        for comment in comments
        if comment.parent_id is None or comment.parent_id not in known_ids
    ]

    order: list[int] = []
    visited: set[int] = set()
    stack = list(reversed(roots))
    while stack:
        comment_id = stack.pop()
        if comment_id in visited:
            continue  # Defensive: a malformed thread must not loop forever.
        visited.add(comment_id)
        order.append(comment_id)
        stack.extend(reversed(children.get(comment_id, ())))

    # Anything unreachable (only possible if the data contains a cycle) still
    # needs a slot, otherwise the accumulation below would raise a KeyError.
    order.extend(comment.id for comment in comments if comment.id not in visited)
    return order


def parse_comments(rows: Iterable[dict[str, Any]], post_id: int = 0) -> list[Comment]:
    """Turn API comment rows into :class:`Comment` records, skipping bad ones."""
    from .scraper import decode_global_id  # Imported here to avoid a cycle.

    comments = []
    for row in rows:
        try:
            comment_id = decode_global_id(row["id"])
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Skipping a comment we could not parse: %s", error)
            continue

        parent = row.get("parent") or {}
        parent_id = None
        if parent.get("__typename") == "Comment" and parent.get("id"):
            try:
                parent_id = decode_global_id(parent["id"])
            except ValueError:
                parent_id = None  # Treat an unreadable parent as a root.

        user = row.get("user") or {}
        comments.append(
            Comment(
                id=comment_id,
                author=user.get("username") or "(deleted user)",
                score=float(row.get("rating") or 0.0),
                parent_id=parent_id,
                post_id=post_id,
                text=derive_title(row.get("text"), COMMENT_EXCERPT_LENGTH),
                author_rating=float(user.get("rating") or 0.0),
            )
        )
    return comments


def fetch_comments(
    client: GraphQLClient, post_global_id: str
) -> tuple[CommentStats | None, list[Comment]]:
    """Fetch one post's comment tree, as highlights and as enriched comments."""
    from .scraper import decode_global_id  # Imported here to avoid a cycle.

    data = client.execute(POST_COMMENTS_QUERY, {"id": post_global_id})
    node = data.get("node") or {}
    try:
        post_id = decode_global_id(node.get("id") or post_global_id)
    except ValueError:
        post_id = 0  # Links will be wrong rather than the whole post lost.
    return analyze_comments(parse_comments(node.get("comments") or [], post_id))


def fetch_comment_stats(
    client: GraphQLClient, post_global_id: str
) -> CommentStats | None:
    """Just the highlights, for callers with no use for the comments."""
    return fetch_comments(client, post_global_id)[0]
