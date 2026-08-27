from __future__ import annotations

from datetime import datetime

import pytest

from joyreactor_stats import config
from joyreactor_stats.cli import build_parser, output_paths, resolve_period, resolve_target


def parse(*argv: str):
    return build_parser().parse_args(list(argv))


def test_defaults_to_the_cringe_tag_and_all_line():
    assert resolve_target(parse("--last-days", "7")) == (config.DEFAULT_TAG, "ALL")


def test_url_supplies_tag_and_line_type():
    args = parse("--url", "https://joyreactor.cc/tag/anon/best", "--last-days", "7")
    assert resolve_target(args) == ("anon", "BEST")


def test_explicit_tag_and_line_type_win_over_the_url():
    args = parse(
        "--url", "https://joyreactor.cc/tag/anon/best",
        "--tag", "art",
        "--line-type", "NEW",
        "--last-days", "7",
    )
    assert resolve_target(args) == ("art", "NEW")


def test_naive_dates_are_read_as_site_time():
    start, end = resolve_period(parse("--start", "2025-08-01", "--end", "2025-09-01 18:30"))
    assert start == datetime(2025, 8, 1, tzinfo=config.SITE_TIMEZONE)
    assert end == datetime(2025, 9, 1, 18, 30, tzinfo=config.SITE_TIMEZONE)


def test_explicit_offsets_are_kept():
    start, _ = resolve_period(parse("--start", "2025-08-01T00:00:00+00:00"))
    assert start.utcoffset().total_seconds() == 0


def test_last_days_is_relative_to_end():
    start, end = resolve_period(parse("--last-days", "10", "--end", "2025-09-11"))
    assert (end - start).days == 10


def test_start_wins_over_last_days():
    start, _ = resolve_period(parse("--start", "2025-01-01", "--last-days", "3"))
    assert start.year == 2025 and start.month == 1


def test_a_period_is_required():
    with pytest.raises(SystemExit, match="Give a period"):
        resolve_period(parse())


def test_reversed_period_is_rejected():
    with pytest.raises(SystemExit, match="must not be later"):
        resolve_period(parse("--start", "2025-09-01", "--end", "2025-08-01"))


def test_out_dir_expands_to_three_files(tmp_path):
    paths = output_paths(parse("--last-days", "1", "--out-dir", str(tmp_path)))
    assert paths["posts_csv"] == tmp_path / "posts.csv"
    assert paths["authors_csv"] == tmp_path / "authors.csv"
    assert paths["json"] == tmp_path / "report.json"


def test_no_output_options_means_console_only():
    assert set(output_paths(parse("--last-days", "1")).values()) == {None}


# --- asking before collecting comment threads -------------------------------

from joyreactor_stats.cli import (  # noqa: E402
    decide_comment_stats,
    describe_comment_cost,
    prompt_yes_no,
)
from tests.helpers import make_post  # noqa: E402


class Asker:
    """Stands in for input(): replays answers and records the prompts seen."""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError("asked more questions than expected")
        return self.answers.pop(0)


POSTS_WITH_COMMENTS = [make_post(1, comments=5), make_post(2, comments=0)]


def test_explicit_comment_stats_flag_skips_the_question():
    ask = Asker()
    assert decide_comment_stats(parse("--last-days", "1", "--comment-stats"),
                                POSTS_WITH_COMMENTS, ask=ask) is True
    assert ask.prompts == []


def test_explicit_no_comment_stats_flag_skips_the_question():
    ask = Asker()
    assert decide_comment_stats(parse("--last-days", "1", "--no-comment-stats"),
                                POSTS_WITH_COMMENTS, ask=ask) is False
    assert ask.prompts == []


def test_without_a_flag_the_user_is_asked():
    ask = Asker("y")
    args = parse("--last-days", "1")
    assert decide_comment_stats(args, POSTS_WITH_COMMENTS, interactive=True, ask=ask) is True
    assert len(ask.prompts) == 1


def test_answering_no_skips_the_comment_pass():
    ask = Asker("n")
    args = parse("--last-days", "1")
    assert decide_comment_stats(args, POSTS_WITH_COMMENTS, interactive=True, ask=ask) is False


def test_just_pressing_enter_accepts():
    args = parse("--last-days", "1")
    assert decide_comment_stats(args, POSTS_WITH_COMMENTS, interactive=True,
                                ask=Asker("")) is True


def test_no_question_when_no_post_has_comments():
    ask = Asker()
    args = parse("--last-days", "1")
    posts = [make_post(1, comments=0)]
    assert decide_comment_stats(args, posts, interactive=True, ask=ask) is False
    assert ask.prompts == []


def test_non_interactive_runs_skip_comments_instead_of_hanging(caplog):
    ask = Asker()
    args = parse("--last-days", "1")
    with caplog.at_level("WARNING"):
        assert decide_comment_stats(args, POSTS_WITH_COMMENTS, interactive=False,
                                    ask=ask) is False
    assert ask.prompts == []
    assert "no terminal" in caplog.text


def test_unclear_answers_are_asked_again():
    ask = Asker("maybe", "wat", "n")
    args = parse("--last-days", "1")
    assert decide_comment_stats(args, POSTS_WITH_COMMENTS, interactive=True, ask=ask) is False
    assert len(ask.prompts) == 3


def test_closed_input_falls_back_to_the_default():
    def eof(_prompt):
        raise EOFError

    assert prompt_yes_no("go?", default=False, ask=eof) is False
    assert prompt_yes_no("go?", default=True, ask=eof) is True


def test_ctrl_c_at_the_prompt_cancels_the_run():
    def interrupt(_prompt):
        raise KeyboardInterrupt

    with pytest.raises(SystemExit, match="Cancelled"):
        prompt_yes_no("go?", default=True, ask=interrupt)


@pytest.mark.parametrize(
    ("count", "delay", "expected"),
    [
        (1, 0.5, "1 request, ~1 s"),
        (23, 0.5, "23 requests, ~12 s"),
        (300, 0.5, "300 requests, ~3 min"),
    ],
)
def test_comment_cost_estimate(count, delay, expected):
    assert describe_comment_cost(count, delay) == expected
