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
