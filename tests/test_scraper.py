from __future__ import annotations

from datetime import datetime

import pytest

from joyreactor_stats.client import JoyreactorError
from joyreactor_stats.config import SITE_TIMEZONE
from joyreactor_stats.scraper import TagScraper, decode_global_id, parse_tag_url

TAG = "Бенефис кринжа"


def encode(post_id: int) -> str:
    import base64

    return base64.b64encode(f"Post:{post_id}".encode()).decode()


def api_row(
    post_id: int,
    created_at: str,
    *,
    author: str = "Раввин",
    rating: float = 1.0,
    author_rating: float = 4236.31,
):
    return {
        "id": encode(post_id),
        "createdAt": created_at,
        "rating": rating,
        "ratingGeneral": 0,
        "commentsCount": 3,
        "text": f"<p>post {post_id}</p>",
        "nsfw": False,
        "banned": False,
        "user": {"username": author, "rating": author_rating},
        "postTags": [{"tag": {"name": TAG}}, {"tag": {"name": "котэ"}}],
    }


class FakeClient:
    """Serves canned listing pages and comment threads, recording what was asked.

    Mirrors the real client closely enough to matter: it counts every request so
    the scraper's budget logic is exercised, and it answers both query shapes.
    """

    def __init__(
        self,
        pages: dict[int, list[dict]],
        count: int = 100,
        comments: dict[int, list[dict]] | None = None,
    ):
        self.pages = pages
        self.count = count
        self.comments = comments or {}
        self.requested_offsets: list[int] = []
        self.requested_comment_posts: list[int] = []
        self.requests_made = 0

    def execute(self, _query, variables):
        self.requests_made += 1
        if "offset" not in variables:  # the per-post comment query
            post_id = decode_global_id(variables["id"])
            self.requested_comment_posts.append(post_id)
            return {"node": {"comments": self.comments.get(post_id, [])}}
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


def api_comment(numeric: int, *, rating=1.0, parent=None, username="user"):
    import base64

    def gid(kind, value):
        return base64.b64encode(f"{kind}:{value}".encode()).decode()

    parent_node = {"__typename": "Post"}
    if parent is not None:
        parent_node = {"__typename": "Comment", "id": gid("Comment", parent)}
    return {
        "id": gid("Comment", numeric),
        "rating": rating,
        "banned": False,
        "user": {"username": username},
        "parent": parent_node,
    }


def test_comment_stats_are_attached_when_enabled():
    listing = api_row(50, "2025-08-31T12:00:00+03:00")
    client = FakeClient(
        {0: [listing], 1: []},
        comments={
            50: [
                api_comment(1, rating=9.0, username="best"),
                api_comment(2, rating=-4.0, parent=1, username="worst"),
                api_comment(3, rating=0.0, parent=2),
            ]
        },
    )
    [post] = TagScraper(client, with_comment_stats=True).fetch_range(
        TAG, moscow("2025-08-01"), moscow("2025-09-01")
    )

    assert client.requested_comment_posts == [50]
    assert post.comment_stats.best_author == "best"
    assert post.comment_stats.worst_author == "worst"
    assert post.comment_stats.most_replied_author == "best"
    assert post.comment_stats.most_replied_direct == 1
    assert post.comment_stats.most_replied_total == 2


def test_no_comment_request_is_made_for_a_post_without_comments():
    listing = api_row(51, "2025-08-31T12:00:00+03:00")
    listing["commentsCount"] = 0
    client = FakeClient({0: [listing], 1: []})
    [post] = TagScraper(client, with_comment_stats=True).fetch_range(
        TAG, moscow("2025-08-01"), moscow("2025-09-01")
    )

    assert client.requested_comment_posts == []
    assert post.comment_stats is None


def test_comment_stats_are_skipped_by_default():
    client = FakeClient({0: [api_row(52, "2025-08-31T12:00:00+03:00")], 1: []})
    [post] = TagScraper(client).fetch_range(TAG, moscow("2025-08-01"), moscow("2025-09-01"))

    assert client.requested_comment_posts == []
    assert post.comment_stats is None


def test_a_failing_comment_thread_leaves_the_post_intact():
    class Failing(FakeClient):
        def execute(self, query, variables):
            if "offset" not in variables:
                raise JoyreactorError("boom")
            return super().execute(query, variables)

    client = Failing({0: [api_row(53, "2025-08-31T12:00:00+03:00")], 1: []})
    [post] = TagScraper(client, with_comment_stats=True).fetch_range(
        TAG, moscow("2025-08-01"), moscow("2025-09-01")
    )

    assert post.id == 53  # the post survives
    assert post.comment_stats is None


def test_the_request_cap_covers_comment_fetches_too():
    rows = [api_row(60 + n, "2025-08-31T12:00:00+03:00") for n in range(3)]
    client = FakeClient(
        {0: rows, 3: []},
        comments={60 + n: [api_comment(n + 1)] for n in range(3)},
    )
    posts = TagScraper(client, max_requests=3, with_comment_stats=True).fetch_range(
        TAG, moscow("2025-08-01"), moscow("2025-09-01")
    )

    # The budget of 3 goes to 2 listing requests (the second confirms the end
    # of the line) plus 1 comment fetch. The posts whose comments were never
    # read are still returned — just without their comment stats.
    assert client.requests_made == 3
    assert len(posts) == 3
    assert [post.comment_stats is not None for post in posts] == [True, False, False]


def test_post_tags_are_parsed_from_the_listing():
    client = FakeClient({0: [api_row(70, "2025-08-31T12:00:00+03:00")], 1: []})
    [post] = list(TagScraper(client).iter_posts(TAG))
    assert post.tags == (TAG, "котэ")


def test_malformed_tag_entries_are_ignored():
    row = api_row(71, "2025-08-31T12:00:00+03:00")
    row["postTags"] = [None, {}, {"tag": None}, {"tag": {"name": ""}}, {"tag": {"name": "ok"}}]
    [post] = list(TagScraper(FakeClient({0: [row], 1: []})).iter_posts(TAG))
    assert post.tags == ("ok",)


def test_missing_post_tags_field_yields_no_tags():
    row = api_row(72, "2025-08-31T12:00:00+03:00")
    del row["postTags"]
    [post] = list(TagScraper(FakeClient({0: [row], 1: []})).iter_posts(TAG))
    assert post.tags == ()


def test_posts_carry_the_author_rating():
    """The listing already returns the author's rating, so it costs no request."""
    client = FakeClient({0: [api_row(1, "2025-08-31T12:00:00+03:00", author_rating=4236.31)]})
    scraper = TagScraper(client)

    post = next(scraper.iter_posts(TAG))

    assert post.author_rating == pytest.approx(4236.31)
    assert post.author_stars == 7


def test_a_missing_author_rating_reads_as_zero():
    row = api_row(1, "2025-08-31T12:00:00+03:00")
    row["user"] = {"username": "someone"}
    scraper = TagScraper(FakeClient({0: [row]}))

    post = next(scraper.iter_posts(TAG))

    assert post.author_rating == 0.0
    assert post.author_stars == 0
