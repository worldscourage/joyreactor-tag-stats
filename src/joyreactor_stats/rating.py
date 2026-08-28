"""Turning a user's numeric rating into the star count the site shows.

The site draws stars with an Ant Design ``Rate`` widget whose value is the
position of the first threshold above the user's rating: below 20 you have no
stars, 20 earns the first, 50 the second, and so on. The thresholds below are
the ones the site's own frontend uses, so our star count matches the profile
page. Rows of ten are only a layout detail there — a rating can be worth more
than ten stars, and we report the plain total.
"""

from __future__ import annotations

#: Rating needed for each successive star, as used by the site itself.
STAR_THRESHOLDS = (
    20,
    50,
    150,
    450,
    1_000,
    1_500,
    2_500,
    4_300,
    6_200,
    8_300,
    10_600,
    13_200,
    16_000,
    19_100,
    22_500,
    26_300,
    30_400,
    34_900,
    39_900,
    45_400,
    60_000,
    100_000,
    220_000,
    500_000,
    1_000_000,
    2_200_000,
    5_000_000,
    10_000_000,
)

MAX_STARS = len(STAR_THRESHOLDS)


def stars_for_rating(rating: float) -> int:
    """How many stars ``rating`` is worth, from 0 to :data:`MAX_STARS`.

    >>> stars_for_rating(19.9), stars_for_rating(20), stars_for_rating(4236.31)
    (0, 1, 7)
    """
    for index, threshold in enumerate(STAR_THRESHOLDS):
        if rating < threshold:
            return index
    # Off the end of the site's table; nobody is there yet, but clamp anyway.
    return MAX_STARS
