from __future__ import annotations

import csv
import json

from joyreactor_stats.exporters import (
    format_authors_table,
    format_posts_table,
    write_authors_csv,
    write_json,
    write_posts_csv,
)
from joyreactor_stats.stats import summarize_by_author


def test_posts_csv_roundtrip(tmp_path, sample_posts):
    path = tmp_path / "nested" / "posts.csv"
    write_posts_csv(sample_posts, path)

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == len(sample_posts)
    assert rows[0]["author"] == "Раввин"
    assert rows[0]["score"] == "75.5"
    assert rows[0]["url"].endswith("/post/1")


def test_authors_csv_has_one_row_per_author(tmp_path, sample_posts):
    path = tmp_path / "authors.csv"
    write_authors_csv(summarize_by_author(sample_posts), path)

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["author"] for row in rows] == ["Раввин", "Culexus"]
    assert rows[0]["posts"] == "3"


def test_json_report_contains_meta_posts_and_authors(tmp_path, sample_posts):
    path = tmp_path / "report.json"
    write_json(
        path,
        meta={"tag": "Бенефис кринжа"},
        posts=sample_posts,
        authors=summarize_by_author(sample_posts),
    )

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["meta"]["tag"] == "Бенефис кринжа"
    assert len(document["posts"]) == 5
    assert len(document["authors"]) == 2


def test_tables_render_headers_and_respect_the_limit(sample_posts):
    posts_table = format_posts_table(sample_posts, limit=2)
    assert "Author" in posts_table
    assert "and 3 more posts" in posts_table

    authors_table = format_authors_table(summarize_by_author(sample_posts))
    assert "Min" in authors_table and "Max" in authors_table and "Sum" in authors_table
    assert "Раввин" in authors_table


def test_tables_handle_no_data():
    assert format_posts_table([]) == "(nothing to show)"
    assert format_authors_table([]) == "(nothing to show)"


def test_posts_csv_carries_the_author_rating_and_stars(tmp_path, sample_posts):
    path = tmp_path / "posts.csv"
    write_posts_csv(sample_posts, path)

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["author_rating"] == "20619.87"
    assert rows[0]["author_stars"] == "14"


def test_authors_csv_carries_the_author_rating_and_stars(tmp_path, sample_posts):
    path = tmp_path / "authors.csv"
    write_authors_csv(summarize_by_author(sample_posts), path)

    with path.open(encoding="utf-8-sig", newline="") as handle:
        by_author = {row["author"]: row for row in csv.DictReader(handle)}

    assert by_author["Раввин"]["author_stars"] == "14"
    assert by_author["Culexus"]["author_rating"] == "628.23"
    assert by_author["Culexus"]["author_stars"] == "4"


def test_tables_show_stars(sample_posts):
    posts_table = format_posts_table(sample_posts)
    authors_table = format_authors_table(summarize_by_author(sample_posts))

    assert "Stars" in posts_table
    assert "★×14" in posts_table
    assert "★★★★" in authors_table  # Culexus, at four stars, fits as symbols.
