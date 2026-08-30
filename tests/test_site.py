"""Counting the site's own output, and the share the tag took of it."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta

import pytest

from joyreactor_stats.cli import describe_site_share
from joyreactor_stats.config import SITE_TIMEZONE
from joyreactor_stats.exporters import format_site_share
from joyreactor_stats.site import FEED_LIMIT, SiteCoverage, count_site_posts, tag_posts_between
from tests.helpers import make_post

#: The moment tests/helpers.make_post counts its posts back from.
NOON = datetime(2025, 8, 31, 12, 0, tzinfo=SITE_TIMEZONE)


def at(minutes_before_noon: int) -> datetime:
    return NOON - timedelta(minutes=minutes_before_noon)


class FakeSearchClient:
    """Serves a site feed newest-first, ten to a page, as the real one does."""

    def __init__(self, moments: list[datetime]):
        self.moments = moments
        self.requests_made = 0

    def execute(self, query, variables):
        self.requests_made += 1
        offset = variables["offset"]
        page = self.moments[offset : offset + 10]
        return {
            "search": {
                "postPager": {
                    "count": len(self.moments),
                    "posts": [
                        {
                            "id": base64.b64encode(f"Post:{index}".encode()).decode(),
                            "createdAt": moment.isoformat(),
                        }
                        for index, moment in enumerate(page)
                    ],
                }
            }
        }


def feed(*minutes: int) -> FakeSearchClient:
    return FakeSearchClient([at(value) for value in minutes])


def test_counts_the_posts_inside_the_window():
    client = feed(*range(0, 200, 10))  # one post every ten minutes, newest first
    coverage = count_site_posts(client, at(50), NOON)

    assert coverage.posts == 6  # 0, 10, 20, 30, 40 and 50 minutes ago
    assert coverage.complete


def test_posts_newer_than_the_window_are_skipped_not_counted():
    client = feed(0, 10, 20, 30)
    coverage = count_site_posts(client, at(30), at(15))

    assert coverage.posts == 2  # only the 20- and 30-minute-old ones


def test_the_walk_stops_as_soon_as_it_passes_the_start():
    client = feed(*range(0, 1000, 10))
    count_site_posts(client, at(50), NOON)

    # Six posts in range plus the older one that ended it: one page suffices.
    assert client.requests_made == 1


def test_a_stale_index_limits_how_far_forward_the_answer_reaches():
    """The real feed lags live by hours, so its newest post bounds the window."""
    client = feed(300, 310, 320, 900)
    coverage = count_site_posts(client, at(600), NOON)

    assert not coverage.complete
    assert coverage.covered_to == at(300)  # not NOON: the index knows nothing newer
    assert coverage.covered_from == at(600)


def test_a_feed_that_runs_dry_before_the_start_reports_how_far_it_got():
    client = feed(0, 10, 20)
    coverage = count_site_posts(client, at(999), NOON)

    assert coverage.posts == 3
    assert not coverage.complete
    assert coverage.covered_from == at(20)


def test_the_walk_gives_up_at_the_feed_limit():
    client = FakeSearchClient([at(value) for value in range(0, FEED_LIMIT + 500)])
    coverage = count_site_posts(client, at(FEED_LIMIT + 400), NOON)

    assert not coverage.complete
    assert client.requests_made == FEED_LIMIT // 10


def test_a_backwards_window_is_refused():
    with pytest.raises(ValueError, match="start must not be later than end"):
        count_site_posts(feed(0), NOON, at(60))


def test_a_silent_period_has_no_share_rather_than_a_division_by_zero():
    coverage = SiteCoverage(0, at(60), NOON, complete=True)

    assert coverage.share_of(0) is None


def test_the_share_is_a_plain_percentage():
    coverage = SiteCoverage(200, at(60), NOON, complete=True)

    assert coverage.share_of(50) == pytest.approx(25.0)


# --- turning coverage into the reported figure ---------------------------------


def test_a_complete_count_compares_the_whole_selection():
    posts = [make_post(index) for index in range(4)]
    share = describe_site_share(posts, SiteCoverage(40, at(60), NOON, complete=True))

    assert share["tag_posts"] == 4
    assert share["site_posts"] == 40
    assert share["percent"] == pytest.approx(10.0)
    assert share["complete"]


def test_a_partial_count_only_compares_the_posts_it_covers():
    """Otherwise the tag would be measured against a site total it dwarfs."""
    posts = [make_post(1, minutes_ago=10), make_post(2, minutes_ago=500)]
    coverage = SiteCoverage(20, at(60), at(5), complete=False)

    share = describe_site_share(posts, coverage)

    assert share["tag_posts"] == 1  # the 500-minute-old post is outside the stretch
    assert share["percent"] == pytest.approx(5.0)
    assert not share["complete"]


def test_no_share_is_reported_when_it_was_not_asked_for():
    assert describe_site_share([make_post(1)], None) is None


def test_the_console_line_states_the_numbers_behind_the_percentage():
    share = describe_site_share(
        [make_post(1)], SiteCoverage(50, at(60), NOON, complete=True)
    )

    assert format_site_share(share) == "Share of the site: 1 of 50 posts (2.00%)"


def test_a_partial_console_line_admits_what_it_covers():
    share = describe_site_share(
        [make_post(1, minutes_ago=10)], SiteCoverage(50, at(60), at(5), complete=False)
    )
    line = format_site_share(share)

    assert "as far as the site feed reaches" in line
    assert "2025-08-31T11:00 … 2025-08-31T11:55" in line


def test_a_silent_period_says_so_instead_of_showing_a_percentage():
    share = describe_site_share([], SiteCoverage(0, at(60), NOON, complete=True))

    assert "nothing was posted" in format_site_share(share)


def test_tag_posts_between_counts_only_the_covered_stretch():
    posts = [
        make_post(1, minutes_ago=0),
        make_post(2, minutes_ago=30),
        make_post(3, minutes_ago=90),
    ]

    assert tag_posts_between(posts, at(60), NOON) == 2
