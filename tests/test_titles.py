"""The postprocess pass that titles text-less posts from their tags."""

from __future__ import annotations

from joyreactor_stats.text import fill_missing_titles
from tests.helpers import make_post

# Every post in a tag line carries the tag itself, so it is always "common".
TAG = "Бенефис кринжа"


def titles(posts) -> list[str]:
    return [post.title for post in posts]


def test_posts_that_already_have_a_title_are_left_alone():
    posts = [make_post(1, title="real text", tags=(TAG, "котэ"))]
    assert titles(fill_missing_titles(posts)) == ["real text"]


def test_a_textless_post_is_titled_from_its_distinctive_tags():
    posts = [
        make_post(1, title="", tags=(TAG, "хентай", "манга")),
        make_post(2, title="text", tags=(TAG,)),
        make_post(3, title="text", tags=(TAG,)),
    ]
    assert titles(fill_missing_titles(posts))[0] == "хентай, манга"


def test_tags_on_more_than_half_the_selection_are_excluded():
    # 'приколы' sits on 3 of 4 posts (75%) and is dropped; 'котэ' on 1 is kept.
    posts = [
        make_post(1, title="", tags=(TAG, "приколы", "котэ")),
        make_post(2, title="", tags=(TAG, "приколы")),
        make_post(3, title="", tags=(TAG, "приколы")),
        make_post(4, title="", tags=(TAG, "аниме")),
    ]
    assert titles(fill_missing_titles(posts)) == ["котэ", "", "", "аниме"]


def test_a_tag_on_exactly_half_the_selection_is_kept():
    # The rule is *more* than half: 2 of 4 stays.
    posts = [
        make_post(1, title="", tags=("half",)),
        make_post(2, title="", tags=("half",)),
        make_post(3, title="", tags=("other",)),
        make_post(4, title="", tags=("other",)),
    ]
    assert titles(fill_missing_titles(posts)) == ["half", "half", "other", "other"]


def test_a_post_whose_tags_are_all_common_keeps_an_empty_title():
    posts = [make_post(1, title="", tags=(TAG,)), make_post(2, title="", tags=(TAG,))]
    assert titles(fill_missing_titles(posts)) == ["", ""]


def test_tag_order_from_the_site_is_preserved():
    posts = [
        make_post(1, title="", tags=("zebra", "apple", "mango")),
        make_post(2, title="text", tags=()),
    ]
    assert titles(fill_missing_titles(posts))[0] == "zebra, apple, mango"


def test_duplicated_tags_on_one_post_count_once_towards_commonness():
    # A post listing a tag twice must not make it look twice as popular.
    posts = [
        make_post(1, title="", tags=("dup", "dup", "rare")),
        make_post(2, title="", tags=("other",)),
    ]
    assert titles(fill_missing_titles(posts)) == ["dup, dup, rare", "other"]


def test_a_single_post_keeps_its_tags_because_nothing_can_be_common():
    posts = [make_post(1, title="", tags=(TAG, "котэ"))]
    assert titles(fill_missing_titles(posts)) == [f"{TAG}, котэ"]


def test_the_threshold_is_configurable():
    posts = [
        make_post(1, title="", tags=("one_of_three",)),
        make_post(2, title="", tags=("shared",)),
        make_post(3, title="", tags=("shared",)),
    ]
    # 'shared' is on 2 of 3 (67%): kept at 0.7, dropped at 0.5.
    assert titles(fill_missing_titles(posts, common_tag_share=0.7))[1] == "shared"
    assert titles(fill_missing_titles(posts, common_tag_share=0.5))[1] == ""


def test_a_share_of_one_keeps_every_tag():
    posts = [make_post(1, title="", tags=("all",)), make_post(2, title="", tags=("all",))]
    assert titles(fill_missing_titles(posts, common_tag_share=1)) == ["all", "all"]


def test_long_tag_lists_are_truncated():
    posts = [
        make_post(1, title="", tags=tuple(f"tag{n}" for n in range(40))),
        make_post(2, title="text"),
    ]
    title = fill_missing_titles(posts, max_length=30)[0].title
    assert len(title) == 30
    assert title.endswith("…")


def test_no_posts_is_not_an_error():
    assert fill_missing_titles([]) == []


def test_posts_without_tags_are_unchanged():
    posts = [make_post(1, title=""), make_post(2, title="")]
    assert titles(fill_missing_titles(posts)) == ["", ""]
