from __future__ import annotations

import base64

from joyreactor_stats.comments import count_replies, parse_comments, summarize_comments
from joyreactor_stats.models import Comment


def comment(comment_id: int, score: float = 0.0, parent: int | None = None, author: str = "u"):
    return Comment(id=comment_id, author=author, score=score, parent_id=parent)


def tree() -> list[Comment]:
    """A thread with two roots and three levels of nesting.

    1 (+5)              root
    ├── 2 (-3)
    │   ├── 4 (+1)
    │   └── 5 (+2)
    │       └── 6 (0)
    └── 3 (+10)
    7 (0)               root
    """
    return [
        comment(1, 5.0, author="alice"),
        comment(2, -3.0, parent=1, author="bob"),
        comment(3, 10.0, parent=1, author="carol"),
        comment(4, 1.0, parent=2, author="dave"),
        comment(5, 2.0, parent=2, author="erin"),
        comment(6, 0.0, parent=5, author="frank"),
        comment(7, 0.0, author="grace"),
    ]


def test_no_comments_means_no_stats():
    assert summarize_comments([]) is None


def test_best_and_worst_comment():
    stats = summarize_comments(tree())
    assert (stats.best_author, stats.best_score) == ("carol", 10.0)
    assert (stats.worst_author, stats.worst_score) == ("bob", -3.0)


def test_direct_replies_count_only_immediate_children():
    direct, _ = count_replies(tree())
    assert direct == {1: 2, 2: 2, 3: 0, 4: 0, 5: 1, 6: 0, 7: 0}


def test_recursive_replies_count_the_whole_subtree():
    _, total = count_replies(tree())
    assert total == {1: 5, 2: 3, 3: 0, 4: 0, 5: 1, 6: 0, 7: 0}


def test_most_replied_comment_reports_both_counts():
    stats = summarize_comments(tree())
    assert stats.most_replied_author == "alice"
    assert stats.most_replied_direct == 2
    assert stats.most_replied_total == 5


def test_most_replied_prefers_the_deeper_thread_over_more_direct_replies():
    # 'shallow' has 3 direct replies and nothing below them; 'deep' has 1 direct
    # reply but a chain underneath, so it wins on the recursive count.
    comments = [
        comment(1, author="shallow"),
        comment(2, parent=1),
        comment(3, parent=1),
        comment(4, parent=1),
        comment(10, author="deep"),
        comment(11, parent=10),
        comment(12, parent=11),
        comment(13, parent=12),
        comment(14, parent=13),
    ]
    stats = summarize_comments(comments)
    assert stats.most_replied_author == "deep"
    assert (stats.most_replied_direct, stats.most_replied_total) == (1, 4)


def test_a_single_comment_has_no_replies():
    stats = summarize_comments([comment(1, 7.5, author="solo")])
    assert stats.best_author == stats.worst_author == "solo"
    assert (stats.most_replied_direct, stats.most_replied_total) == (0, 0)


def test_ties_are_broken_towards_the_earlier_comment():
    comments = [comment(1, 5.0, author="first"), comment(2, 5.0, author="second")]
    stats = summarize_comments(comments)
    assert stats.best_author == "first"
    assert stats.worst_author == "first"


def test_a_reply_to_a_missing_parent_is_treated_as_a_root():
    # Happens when a parent comment was deleted: the reply must not be lost.
    direct, total = count_replies([comment(1), comment(2, parent=999)])
    assert direct == {1: 0, 2: 0}
    assert total == {1: 0, 2: 0}


def test_a_cycle_does_not_hang_or_raise():
    direct, total = count_replies([comment(1, parent=2), comment(2, parent=1)])
    assert set(total) == {1, 2}


def test_a_very_deep_thread_does_not_blow_the_stack():
    depth = 3000
    comments = [comment(1)] + [comment(i, parent=i - 1) for i in range(2, depth + 1)]
    _, total = count_replies(comments)
    assert total[1] == depth - 1


def encode(kind: str, numeric: int) -> str:
    return base64.b64encode(f"{kind}:{numeric}".encode()).decode()


def api_comment(numeric: int, *, rating=1.0, parent=None, username="user"):
    parent_node = {"__typename": "Post"}
    if parent is not None:
        parent_node = {"__typename": "Comment", "id": encode("Comment", parent)}
    return {
        "id": encode("Comment", numeric),
        "rating": rating,
        "banned": False,
        "user": {"username": username},
        "parent": parent_node,
    }


def test_parse_comments_reads_ids_scores_and_parents():
    parsed = parse_comments([api_comment(10), api_comment(11, parent=10, rating=-2.5)])
    assert [c.id for c in parsed] == [10, 11]
    assert parsed[0].parent_id is None  # replies to the post itself
    assert parsed[1].parent_id == 10
    assert parsed[1].score == -2.5


def test_parse_comments_skips_unreadable_rows():
    parsed = parse_comments([{"id": "not-base64!"}, api_comment(12)])
    assert [c.id for c in parsed] == [12]


def test_parse_comments_handles_a_deleted_author_and_missing_rating():
    row = api_comment(13)
    row["user"] = None
    row["rating"] = None
    [parsed] = parse_comments([row])
    assert parsed.author == "(deleted user)"
    assert parsed.score == 0.0


def test_parse_comments_treats_an_unreadable_parent_as_a_root():
    row = api_comment(14, parent=1)
    row["parent"] = {"__typename": "Comment", "id": "garbage!"}
    [parsed] = parse_comments([row])
    assert parsed.parent_id is None
