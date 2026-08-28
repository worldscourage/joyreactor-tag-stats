"""The rating → stars mapping, checked against real profile pages."""

from __future__ import annotations

import pytest

from joyreactor_stats.exporters import format_stars
from joyreactor_stats.rating import MAX_STARS, STAR_THRESHOLDS, stars_for_rating


def test_a_fresh_account_has_no_stars():
    assert stars_for_rating(0.0) == 0


def test_the_first_star_needs_twenty_rating():
    assert stars_for_rating(19.99) == 0
    assert stars_for_rating(20.0) == 1


def test_negative_ratings_stay_at_zero_stars():
    assert stars_for_rating(-500.0) == 0


@pytest.mark.parametrize(
    ("rating", "stars"),
    [
        # Read off real profile pages while working this out, so the mapping is
        # pinned to what the site actually draws, not to our reading of it.
        (4.43, 0),
        (39.97, 1),
        (263.44, 3),
        (851.18, 4),
        (2078.44, 6),
        (4236.31, 7),
        (5260.06, 8),
        (18338.08, 13),
        (20619.87, 14),
    ],
)
def test_matches_the_stars_shown_on_the_site(rating, stars):
    assert stars_for_rating(rating) == stars


def test_every_threshold_earns_exactly_one_more_star():
    for index, threshold in enumerate(STAR_THRESHOLDS):
        assert stars_for_rating(threshold) == index + 1


def test_an_impossible_rating_is_clamped_to_the_top():
    assert stars_for_rating(STAR_THRESHOLDS[-1] * 10) == MAX_STARS


def test_stars_are_spelled_out_while_they_fit():
    assert format_stars(0) == ""
    assert format_stars(3) == "★★★"
    assert format_stars(10) == "★" * 10


def test_long_star_runs_are_folded_into_a_count():
    assert format_stars(14) == "★×14"
