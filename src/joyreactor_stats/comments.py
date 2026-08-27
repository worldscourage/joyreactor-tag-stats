"""Per-post comment highlights: the best, the worst, and the most-answered comment.

A post's whole comment tree arrives in a single request, so the work here is
mostly shaping: build the parent → children map, then read three answers out of
it. Everything below the fetch is pure, which keeps it easy to test.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from .client import GraphQLClient
from .models import Comment, CommentStats

logger = logging.getLogger(__name__)

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
        user {
          username
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


def summarize_comments(comments: Sequence[Comment]) -> CommentStats | None:
    """Reduce a post's comments to its three highlights.

    Returns ``None`` for a post with no comments, which is a normal state and
    not an error. Ties are broken in favour of the earlier comment, so repeated
    runs over the same post always agree.
    """
    if not comments:
        return None

    best = max(comments, key=lambda comment: comment.score)
    worst = min(comments, key=lambda comment: comment.score)

    direct, total = count_replies(comments)
    most_replied = max(
        comments,
        key=lambda comment: (total[comment.id], direct[comment.id]),
    )

    return CommentStats(
        best_author=best.author,
        best_score=best.score,
        worst_author=worst.author,
        worst_score=worst.score,
        most_replied_author=most_replied.author,
        most_replied_direct=direct[most_replied.id],
        most_replied_total=total[most_replied.id],
    )


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


def parse_comments(rows: Iterable[dict[str, Any]]) -> list[Comment]:
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
            )
        )
    return comments


def fetch_comment_stats(
    client: GraphQLClient, post_global_id: str
) -> CommentStats | None:
    """Fetch one post's comment tree and reduce it to its highlights."""
    data = client.execute(POST_COMMENTS_QUERY, {"id": post_global_id})
    node = data.get("node") or {}
    return summarize_comments(parse_comments(node.get("comments") or []))
