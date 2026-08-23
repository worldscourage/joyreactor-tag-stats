from __future__ import annotations

import pytest

from joyreactor_stats.models import Post
from tests.helpers import make_post


@pytest.fixture
def sample_posts() -> list[Post]:
    return [
        make_post(1, "Раввин", 75.5, comments=60, minutes_ago=0),
        make_post(2, "Раввин", -10.0, comments=4, minutes_ago=60),
        make_post(3, "Раввин", 16.5, comments=27, minutes_ago=120),
        make_post(4, "Culexus", -5.0, comments=1, minutes_ago=180),
        make_post(5, "Culexus", 20.0, comments=8, minutes_ago=240),
    ]
