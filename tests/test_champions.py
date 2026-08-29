"""The champions post-process: what gets picked, and how it reads."""

from __future__ import annotations

import json

import pytest

from joyreactor_stats.champions import (
    CHAPTER_KEYS,
    TOP_COMMENTS,
    TOP_POSTS,
    build_champions,
    load_report,
    plural,
    render_champions,
    whole_rating,
    write_all,
)
from joyreactor_stats.cli import champions_main
from tests.helpers import make_comment, make_post


def chapter(chapters, key):
    return next(item for item in chapters if item.key == key)


def test_every_chapter_is_present_and_in_order():
    chapters = build_champions([], [])

    assert tuple(item.key for item in chapters) == CHAPTER_KEYS


# --- posts -------------------------------------------------------------------


def test_top_and_bottom_posts_pick_the_extremes():
    posts = [make_post(index, score=float(index)) for index in range(1, 21)]
    chapters = build_champions(posts, [])

    top = chapter(chapters, "top_posts").entries
    bottom = chapter(chapters, "bottom_posts").entries

    assert len(top) == TOP_POSTS
    assert [entry.score for entry in top] == list(range(20, 10, -1))
    assert [entry.score for entry in bottom] == list(range(1, 11))


def test_a_short_run_lists_every_post_it_has():
    posts = [make_post(1, score=5.0), make_post(2, score=-1.0)]
    chapters = build_champions(posts, [])

    assert len(chapter(chapters, "top_posts").entries) == 2


def test_a_post_entry_carries_everything_a_reader_needs():
    posts = [make_post(7, "Раввин", 12.5, title="A title", author_rating=20619.87)]
    entry = chapter(build_champions(posts, []), "top_posts").entries[0]

    assert entry.kind == "post"
    assert entry.title == "A title"
    assert entry.url == "https://joyreactor.cc/post/7"
    assert entry.score == pytest.approx(12.5)
    assert entry.author == "Раввин"
    assert entry.author_stars == 14


def test_ties_are_broken_by_id_so_reruns_agree():
    posts = [make_post(3, score=1.0), make_post(1, score=1.0), make_post(2, score=1.0)]
    entries = chapter(build_champions(posts, []), "top_posts").entries

    assert [entry.url.rsplit("/", 1)[-1] for entry in entries] == ["1", "2", "3"]


def test_empty_input_says_why_it_is_empty():
    top = chapter(build_champions([], []), "top_posts")

    assert top.entries == ()
    assert top.empty_reason == "empty_no_posts"


def test_most_commented_posts_rank_by_comments_not_by_score():
    posts = [
        make_post(1, "quiet_hit", 500.0, comments=1),
        make_post(2, "argument", -80.0, comments=90),
        make_post(3, "middling", 10.0, comments=40),
    ]
    entries = chapter(build_champions(posts, []), "most_commented_posts").entries

    assert [entry.author for entry in entries] == ["argument", "middling", "quiet_hit"]
    assert [entry.comments for entry in entries] == [90, 40, 1]


def test_posts_nobody_commented_on_are_left_out():
    posts = [make_post(1, "silent", 5.0, comments=0), make_post(2, "talked", 5.0, comments=3)]
    entries = chapter(build_champions(posts, []), "most_commented_posts").entries

    assert [entry.author for entry in entries] == ["talked"]


def test_the_most_commented_chapter_stops_at_ten():
    posts = [make_post(index, comments=index) for index in range(1, 21)]
    entries = chapter(build_champions(posts, []), "most_commented_posts").entries

    assert len(entries) == TOP_POSTS
    assert [entry.comments for entry in entries] == list(range(20, 10, -1))


def test_the_comment_count_is_written_out_in_both_languages():
    posts = [make_post(1, "a", 1.0, comments=1)]
    chapters = build_champions(posts, [])

    assert "1 comment\n" in render_champions(chapters, language="en")
    assert "1 комментарий" in render_champions(chapters, language="ru")


def test_only_the_comment_count_chapter_states_a_count():
    posts = [make_post(1, "a", 1.0, comments=7)]
    chapters = build_champions(posts, [])

    assert chapter(chapters, "top_posts").entries[0].comments is None
    assert chapter(chapters, "most_commented_posts").entries[0].comments == 7


# --- worst post per star tier ------------------------------------------------


def test_each_star_tier_contributes_its_worst_post():
    posts = [
        # Two authors on one star (ratings 20 and 30), two on four stars.
        make_post(1, "a", -5.0, author_rating=20.0),
        make_post(2, "b", -9.0, author_rating=30.0),
        make_post(3, "c", 2.0, author_rating=500.0),
        make_post(4, "d", -1.0, author_rating=600.0),
    ]
    entries = chapter(build_champions(posts, []), "worst_post_per_star_tier").entries

    assert [entry.author for entry in entries] == ["b", "d"]
    assert [entry.author_stars for entry in entries] == [1, 4]


def test_tiers_are_listed_from_the_lowest_up():
    posts = [
        make_post(1, "high", 0.0, author_rating=6200.0),
        make_post(2, "low", 0.0, author_rating=0.0),
        make_post(3, "mid", 0.0, author_rating=450.0),
    ]
    entries = chapter(build_champions(posts, []), "worst_post_per_star_tier").entries

    # A rating sitting exactly on a threshold has already earned that star.
    assert [entry.author_stars for entry in entries] == [0, 4, 9]


def test_authors_at_ten_stars_or_more_are_left_out():
    posts = [
        make_post(1, "star10", -50.0, author_rating=8300.0),
        make_post(2, "star9", 1.0, author_rating=6200.0),
    ]
    entries = chapter(build_champions(posts, []), "worst_post_per_star_tier").entries

    assert [entry.author for entry in entries] == ["star9"]


def test_a_tier_with_one_post_lists_it_however_good_it_was():
    posts = [make_post(1, "solo", 99.0, author_rating=20.0)]
    entries = chapter(build_champions(posts, []), "worst_post_per_star_tier").entries

    assert [entry.score for entry in entries] == [pytest.approx(99.0)]


# --- comments ----------------------------------------------------------------


def test_comment_chapters_rank_across_every_post():
    """The three loudest comments may all sit under one post — and often do."""
    comments = [
        make_comment(1, "a", 10.0, post_id=100),
        make_comment(2, "b", 9.0, post_id=100),
        make_comment(3, "c", 8.0, post_id=100),
        make_comment(4, "d", 1.0, post_id=200),
    ]
    entries = chapter(build_champions([], comments), "best_comments").entries

    assert [entry.author for entry in entries] == ["a", "b", "c"]
    assert len(entries) == TOP_COMMENTS


def test_worst_comments_take_the_other_end():
    comments = [
        make_comment(1, "a", 5.0),
        make_comment(2, "b", -20.0),
        make_comment(3, "c", -30.0),
    ]
    entries = chapter(build_champions([], comments), "worst_comments").entries

    assert [entry.author for entry in entries] == ["c", "b", "a"]


def test_reply_chapters_rank_by_their_own_count():
    comments = [
        make_comment(1, "wide", 0.0, direct_replies=9, total_replies=9),
        make_comment(2, "deep", 0.0, direct_replies=1, total_replies=40),
        make_comment(3, "small", 0.0, direct_replies=2, total_replies=3),
    ]
    chapters = build_champions([], comments)

    assert [e.author for e in chapter(chapters, "most_direct_replies").entries] == [
        "wide",
        "small",
        "deep",
    ]
    assert [e.author for e in chapter(chapters, "most_total_replies").entries] == [
        "deep",
        "wide",
        "small",
    ]


def test_comments_nobody_answered_are_not_reply_champions():
    comments = [make_comment(1, "quiet", 5.0)]
    chapters = build_champions([], comments)

    assert chapter(chapters, "most_direct_replies").entries == ()
    assert chapter(chapters, "most_total_replies").entries == ()


def test_a_comment_entry_links_to_its_place_in_the_post():
    comments = [make_comment(456, "a", 1.0, post_id=123, text="Excerpt")]
    entry = chapter(build_champions([], comments), "best_comments").entries[0]

    assert entry.kind == "comment"
    assert entry.url == "https://joyreactor.cc/post/123#comment456"
    assert entry.title == "Excerpt"


def test_uncollected_comments_read_differently_from_absent_ones():
    looked = chapter(build_champions([], [], comments_collected=True), "best_comments")
    never = chapter(build_champions([], [], comments_collected=False), "best_comments")

    assert looked.empty_reason is None
    assert never.empty_reason == "empty_no_comments"


# --- rendering ---------------------------------------------------------------


def test_the_text_report_carries_the_facts_of_each_entry():
    posts = [make_post(7, "Раввин", 12.5, title="A title", author_rating=20619.87)]
    text = render_champions(build_champions(posts, []), language="en")

    assert "A title" in text
    assert "+12.50" in text
    assert "https://joyreactor.cc/post/7" in text
    assert "14 stars (rating 20620)" in text


def test_one_star_is_not_one_stars():
    posts = [make_post(1, "a", 1.0, author_rating=25.0)]

    assert "1 star (" in render_champions(build_champions(posts, []), language="en")


def test_russian_uses_russian_plurals():
    posts = [make_post(1, "a", 1.0, author_rating=25.0)]
    text = render_champions(build_champions(posts, []), language="ru")

    assert "ЧЕМПИОНЫ" in text
    assert "1 звезда (рейтинг 25)" in text


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "звезда"), (2, "звезды"), (5, "звёзд"), (11, "звёзд"), (21, "звезда")],
)
def test_russian_plural_rule(count, expected):
    assert plural(count, ("звезда", "звезды", "звёзд"), "ru") == expected


def test_a_missing_title_is_explained_in_the_reader_language():
    posts = [make_post(1, "a", 1.0, title="")]

    assert "(no text" in render_champions(build_champions(posts, []), language="en")
    assert "(без текста" in render_champions(build_champions(posts, []), language="ru")


def test_an_empty_chapter_states_its_reason():
    text = render_champions(build_champions([], [], comments_collected=False))

    assert "--comment-stats" in text


def test_a_rating_on_a_half_rounds_the_same_way_every_time():
    # The report keeps two decimals, so a live 4514.5004 becomes 4514.5 there.
    # Both must print alike, which banker's rounding would not do.
    assert whole_rating(4514.5004) == whole_rating(4514.5) == 4515


# --- files and the separate command -------------------------------------------


def test_write_all_produces_the_three_files(tmp_path):
    posts = [make_post(1, "a", 1.0)]
    paths = write_all(build_champions(posts, []), tmp_path, meta={"tag": "t"})

    assert [path.name for path in paths] == [
        "champions.json",
        "champions.txt",
        "champions-ru.txt",
    ]
    assert all(path.exists() for path in paths)


def test_the_json_names_each_chapter_in_both_languages(tmp_path):
    posts = [make_post(1, "a", 1.0, author_rating=25.0)]
    write_all(build_champions(posts, []), tmp_path)
    document = json.loads((tmp_path / "champions.json").read_text(encoding="utf-8"))

    first = document["chapters"][0]
    assert first["key"] == "top_posts"
    assert first["title"] == f"Top {TOP_POSTS} posts"
    assert first["title_ru"] == f"Топ-{TOP_POSTS} постов"
    assert first["entries"][0]["author_stars"] == 1


def test_champions_can_be_rebuilt_from_a_report(tmp_path, sample_posts):
    from joyreactor_stats.exporters import write_json
    from joyreactor_stats.stats import summarize_by_author

    comments = [make_comment(9, "loud", 3.0, post_id=1, direct_replies=2, total_replies=5)]
    report = tmp_path / "report.json"
    write_json(
        report,
        meta={"tag": "t"},
        posts=sample_posts,
        authors=summarize_by_author(sample_posts),
        comments=comments,
    )

    posts, loaded_comments, meta = load_report(report)

    assert len(posts) == len(sample_posts)
    assert posts[0].author == sample_posts[0].author
    assert posts[0].author_stars == sample_posts[0].author_stars
    assert [item.author for item in loaded_comments] == ["loud"]
    assert loaded_comments[0].total_replies == 5
    assert meta["tag"] == "t"


def test_the_separate_command_writes_next_to_the_report(tmp_path, sample_posts, capsys):
    from joyreactor_stats.exporters import write_json
    from joyreactor_stats.stats import summarize_by_author

    report = tmp_path / "report.json"
    write_json(
        report,
        meta={"tag": "t"},
        posts=sample_posts,
        authors=summarize_by_author(sample_posts),
    )

    assert champions_main([str(report)]) == 0

    assert (tmp_path / "champions.txt").exists()
    assert (tmp_path / "champions-ru.txt").exists()
    assert "Written:" in capsys.readouterr().out


def test_the_separate_command_refuses_a_file_it_did_not_write(tmp_path):
    stranger = tmp_path / "stranger.json"
    stranger.write_text('{"hello": "world"}', encoding="utf-8")

    with pytest.raises(SystemExit):
        champions_main([str(stranger)])


def test_the_separate_command_reports_a_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        champions_main([str(tmp_path / "nope.json")])
