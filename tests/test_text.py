from __future__ import annotations

import pytest

from joyreactor_stats.text import derive_title


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (None, ""),
        ("", ""),
        ("&attribute_insert_1&", ""),
        ("<p>&attribute_insert_1&</p>", ""),
        ("<p>Простой текст</p>", "Простой текст"),
        ("<h3>476 постов за неделю! </h3>&attribute_insert_1&", "476 постов за неделю!"),
        ("<p>Первая строка</p><p>Вторая строка</p>", "Первая строка Вторая строка"),
        ("<p>a &amp; b &lt;c&gt;</p>", "a & b <c>"),
        ("<p>Line<br>break</p>", "Line break"),
        ("<p>  spaced\n\ttext  </p>", "spaced text"),
    ],
)
def test_derive_title(body, expected):
    assert derive_title(body) == expected


def test_long_titles_are_truncated_with_an_ellipsis():
    title = derive_title("<p>" + "x" * 200 + "</p>", max_length=20)
    assert len(title) == 20
    assert title.endswith("…")
