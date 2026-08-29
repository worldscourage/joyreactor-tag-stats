from __future__ import annotations

import pytest

from joyreactor_stats.stats import overall_totals, summarize_by_author
from tests.helpers import make_post


def test_summary_computes_min_max_sum_and_count(sample_posts):
    by_author = {item.author: item for item in summarize_by_author(sample_posts)}

    rabbi = by_author["Раввин"]
    assert rabbi.posts == 3
    assert rabbi.score_min == -10.0
    assert rabbi.score_max == 75.5
    assert rabbi.score_sum == pytest.approx(82.0)
    assert rabbi.score_avg == pytest.approx(82.0 / 3)
    assert rabbi.comments_sum == 91
    assert rabbi.first_post_at < rabbi.last_post_at


def test_summary_is_sorted_by_score_sum_descending(sample_posts):
    assert [item.author for item in summarize_by_author(sample_posts)] == [
        "Раввин",
        "Culexus",
    ]


def test_summary_can_sort_by_other_keys(sample_posts):
    by_max = summarize_by_author(sample_posts, sort_by="score_max")
    assert by_max[0].author == "Раввин"

    by_name = summarize_by_author(sample_posts, sort_by="author")
    assert [item.author for item in by_name] == ["Culexus", "Раввин"]


def test_summary_rejects_unknown_sort_key(sample_posts):
    with pytest.raises(ValueError, match="Unknown sort key"):
        summarize_by_author(sample_posts, sort_by="karma")


def test_single_post_author_has_equal_min_max_sum():
    [summary] = summarize_by_author([make_post(9, "solo", -3.5)])
    assert (summary.score_min, summary.score_max, summary.score_sum) == (-3.5, -3.5, -3.5)
    assert summary.posts == 1


def test_empty_input_produces_no_summaries_and_zero_totals():
    assert summarize_by_author([]) == []
    assert overall_totals([]) == {
        "posts": 0,
        "authors": 0,
        "score_sum": 0.0,
        "comments_sum": 0,
    }


def test_overall_totals(sample_posts):
    totals = overall_totals(sample_posts)
    assert totals["posts"] == 5
    assert totals["authors"] == 2
    assert totals["comments_sum"] == 100


def test_author_rating_comes_from_their_newest_post():
    posts = [
        make_post(1, "Раввин", 1.0, minutes_ago=0, author_rating=20619.87),
        make_post(2, "Раввин", 1.0, minutes_ago=600, author_rating=19000.0),
    ]
    summary = summarize_by_author(posts)[0]

    assert summary.author_rating == pytest.approx(20619.87)
    assert summary.author_stars == 14


def test_authors_can_be_sorted_by_rating(sample_posts):
    ranked = summarize_by_author(sample_posts, sort_by="author_rating")

    assert [item.author for item in ranked] == ["Раввин", "Culexus"]


def test_positive_and_negative_sums_split_the_total():
    posts = [
        make_post(1, "Раввин", 10.0),
        make_post(2, "Раввин", -4.0),
        make_post(3, "Раввин", 2.5),
        make_post(4, "Раввин", -1.5),
    ]
    summary = summarize_by_author(posts)[0]

    assert summary.score_positive_sum == pytest.approx(12.5)
    assert summary.score_negative_sum == pytest.approx(-5.5)
    assert summary.score_positive_sum + summary.score_negative_sum == pytest.approx(
        summary.score_sum
    )


def test_a_zero_score_post_counts_to_neither_side():
    posts = [make_post(1, "Раввин", 0.0), make_post(2, "Раввин", 3.0)]
    summary = summarize_by_author(posts)[0]

    assert summary.score_positive_sum == pytest.approx(3.0)
    assert summary.score_negative_sum == 0.0


def test_an_author_with_only_downvoted_posts_has_no_positive_sum():
    summary = summarize_by_author([make_post(1, "Раввин", -8.0)])[0]

    assert summary.score_positive_sum == 0.0
    assert summary.score_negative_sum == pytest.approx(-8.0)


def test_authors_can_be_sorted_by_the_new_sums(sample_posts):
    by_plus = summarize_by_author(sample_posts, sort_by="score_positive_sum")
    by_minus = summarize_by_author(sample_posts, sort_by="score_negative_sum")

    # Раввин collected +92.0 against Culexus's +20.0 ...
    assert [item.author for item in by_plus] == ["Раввин", "Culexus"]
    # ... but Culexus was dragged the least, and descending puts them first.
    assert [item.author for item in by_minus] == ["Culexus", "Раввин"]
