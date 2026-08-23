from __future__ import annotations

from datetime import datetime

import pytest

from joyreactor_stats.config import SITE_TIMEZONE
from joyreactor_stats.scraper import TagScraper, decode_global_id, parse_tag_url

TAG = "Бенефис кринжа"


def encode(post_id: int) -> str:
    import base64

    return base64.b64encode(f"Post:{post_id}".encode()).decode()


def api_row(post_id: int, created_at: str, *, author: str = "Раввин", rating: float = 1.0):
    return {
        "id": encode(post_id),
        "createdAt": created_at,
        "rating": rating,
        "ratingGeneral": 0,
        "commentsCount": 3,
        "text": f"<p>post {post_id}</p>",
        "nsfw": False,
        "banned": False,
        "user": {"username": author},
    }


class FakeClient:
    """Serves canned pages and records the offsets the scraper asked for."""

    def __init__(self, pages: dict[int, list[dict]], count: int = 100):
        self.pages = pages
        self.count = count
        self.requested_offsets: list[int] = []

    def execute(self, _query, variables):
        offset = variables["offset"]
        self.requested_offsets.append(offset)
        return {
            "tag": {
                "id": "VGFnOjE=",
                "name": variables["tag"],
                "postPager": {"count": self.count, "posts": self.pages.get(offset, [])},
            }
        }


def moscow(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=SITE_TIMEZONE)


def test_decode_global_id():
    assert decode_global_id("UG9zdDo2MzA5OTE0") == 6309914


@pytest.mark.parametrize("bad", ["not-base64!!", "", "aGVsbG8="])
def test_decode_global_id_rejects_garbage(bad):
    with pytest.raises(ValueError):
        decode_global_id(bad)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://joyreactor.cc/tag/anon/all", ("anon", "ALL")),
        ("https://joyreactor.cc/tag/anon", ("anon", "ALL")),
        ("https://joyreactor.cc/tag/anon/best", ("anon", "BEST")),
        ("https://joyreactor.cc/tag/anon/all/12", ("anon", "ALL")),
        (
            "https://joyreactor.cc/tag/%D0%B0%D0%BD%D0%BE%D0%BD/good",
            ("анон", "GOOD"),
        ),
    ],
)
def test_parse_tag_url(url, expected):
    assert parse_tag_url(url) == expected


def test_parse_tag_url_rejects_other_urls():
    with pytest.raises(ValueError, match="Not a joyreactor tag URL"):
        parse_tag_url("https://joyreactor.cc/post/123")


def test_iter_posts_pages_until_exhausted_and_deduplicates():
    # The API hands out overlapping windows; the scraper must not yield twice.
    client = FakeClient(
        {
            0: [api_row(3, "2025-08-31T12:00:00+03:00"), api_row(2, "2025-08-30T12:00:00+03:00")],
            2: [api_row(2, "2025-08-30T12:00:00+03:00"), api_row(1, "2025-08-29T12:00:00+03:00")],
            4: [],
        }
    )
    posts = list(TagScraper(client).iter_posts(TAG))

    assert [post.id for post in posts] == [3, 2, 1]
    assert client.requested_offsets == [0, 2, 4]


def test_iter_posts_stops_when_a_page_repeats_itself():
    same = [api_row(1, "2025-08-31T12:00:00+03:00")]
    client = FakeClient({0: same, 1: same})
    assert len(list(TagScraper(client).iter_posts(TAG))) == 1


def test_iter_posts_honours_the_request_cap():
    client = FakeClient({offset: [api_row(100 - offset, "2025-08-31T12:00:00+03:00")]
                         for offset in range(0, 10)})
    posts = list(TagScraper(client, max_requests=3).iter_posts(TAG))
    assert len(client.requested_offsets) == 3
    assert len(posts) == 3


def test_fetch_range_keeps_only_the_window_and_stops_early():
    client = FakeClient(
        {
            0: [
                api_row(5, "2025-09-05T10:00:00+03:00"),  # newer than the window
                api_row(4, "2025-08-31T10:00:00+03:00"),  # inside
            ],
            2: [
                api_row(3, "2025-08-30T10:00:00+03:00"),  # inside
                api_row(2, "2025-08-01T10:00:00+03:00"),  # older -> stop here
            ],
            4: [api_row(1, "2024-01-01T10:00:00+03:00")],
        }
    )
    scraper = TagScraper(client)
    posts = scraper.fetch_range(TAG, moscow("2025-08-15"), moscow("2025-09-01"))

    assert [post.id for post in posts] == [4, 3]
    assert client.requested_offsets == [0, 2]  # third page never fetched
    assert scraper.total_posts_in_tag == 100


def test_fetch_range_rejects_a_reversed_period():
    with pytest.raises(ValueError, match="start must not be later"):
        TagScraper(FakeClient({})).fetch_range(TAG, moscow("2025-09-01"), moscow("2025-08-01"))


def test_unparsable_rows_are_skipped_not_fatal():
    rows = [{"id": "broken", "createdAt": None}, api_row(7, "2025-08-31T12:00:00+03:00")]
    client = FakeClient({0: rows, 1: []})
    posts = list(TagScraper(client).iter_posts(TAG))
    assert [post.id for post in posts] == [7]


def test_missing_user_falls_back_to_a_placeholder():
    row = api_row(8, "2025-08-31T12:00:00+03:00")
    row["user"] = None
    posts = list(TagScraper(FakeClient({0: [row], 1: []})).iter_posts(TAG))
    assert posts[0].author == "(deleted user)"
