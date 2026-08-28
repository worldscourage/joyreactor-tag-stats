from __future__ import annotations

import pytest

from joyreactor_stats.models import Post
from tests.helpers import make_post


@pytest.fixture
def sample_posts() -> list[Post]:
    return [
        # Раввин's author rating differs per post so tests can tell which one
        # the summary picked: 20620 sits on the newest post, so it is the current one.
        make_post(1, "Раввин", 75.5, comments=60, minutes_ago=0, author_rating=20619.87),
        make_post(2, "Раввин", -10.0, comments=4, minutes_ago=60, author_rating=20500.0),
        make_post(3, "Раввин", 16.5, comments=27, minutes_ago=120, author_rating=20400.0),
        make_post(4, "Culexus", -5.0, comments=1, minutes_ago=180, author_rating=628.23),
        make_post(5, "Culexus", 20.0, comments=8, minutes_ago=240, author_rating=628.23),
    ]
