"""Site-specific constants and tunable defaults.

Everything here is data, not behaviour: if joyreactor changes an endpoint or we
want to be a friendlier crawler, this is the only file that needs touching.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

#: Public GraphQL endpoint the site's own frontend talks to.
GRAPHQL_URL = "https://api.joyreactor.cc/graphql"

#: Used to build human-clickable post links and as the ``Origin``/``Referer``
#: the API expects from a browser.
SITE_URL = "https://joyreactor.cc"

#: The site renders and stores every timestamp in Moscow time. Naive datetimes
#: coming from the command line are interpreted in this zone so that "give me
#: everything from 2025-08-31" means what the reader of the site would expect.
SITE_TIMEZONE = ZoneInfo("Europe/Moscow")

#: The tag this project was written for: "Бенефис кринжа".
DEFAULT_TAG = "Бенефис кринжа"

#: How many posts the API returns per request. It is not configurable server
#: side; we only use it to advance the offset.
PAGE_SIZE = 10

#: Networking defaults. The pause is per request and deliberately generous:
#: a stats run is never urgent, and hammering someone's site is rude.
REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 1.5

USER_AGENT = (
    "joyreactor-stats/1.0 (+https://github.com/; polite tag statistics collector)"
)

#: Maps the last path segment of a tag URL to the API's PostLineType enum.
LINE_TYPES = {
    "all": "ALL",
    "new": "NEW",
    "good": "GOOD",
    "best": "BEST",
}
