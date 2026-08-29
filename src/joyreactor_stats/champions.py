"""The champions post-process: the standouts of a finished run.

This pass adds no requests. It re-reads what a run already collected and picks
the extremes out of it — the best and worst posts, the loudest comments — into
chapters that are written as one machine-readable file and one readable file per
language.

Building and rendering are kept apart on purpose: :func:`build_champions`
resolves every value a reader could need into flat :class:`Champion` records, so
adding a language means adding a table of words, never touching the selection
logic.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import SITE_URL
from .exporters import format_side_total
from .models import Champion, Chapter, Comment, Post
from .stats import summarize_by_author

#: How many posts each of the two post chapters holds.
TOP_POSTS = 10

#: How many comments each comment chapter holds.
TOP_COMMENTS = 3

#: How many authors each author chapter holds.
TOP_AUTHORS = 3

#: Star tiers below this get their own worst-post entry. Ten is where the site
#: starts a second row of stars, which is as good a line as any to stop at.
STAR_TIER_LIMIT = 10

#: Chapters in the order they are written, and the reason each may be empty.
CHAPTER_KEYS = (
    "top_posts",
    "bottom_posts",
    "most_commented_posts",
    "worst_post_per_star_tier",
    "most_prolific_authors",
    "biggest_absolute_authors",
    "most_downvoted_authors",
    "best_comments",
    "worst_comments",
    "most_direct_replies",
    "most_total_replies",
)

COMMENT_CHAPTERS = frozenset(
    {"best_comments", "worst_comments", "most_direct_replies", "most_total_replies"}
)

LABELS: dict[str, dict[str, Any]] = {
    "en": {
        "document_title": "CHAMPIONS",
        "tag": "Tag",
        "period": "Period",
        "generated_from": "Posts / comments",
        "top_posts": f"Top {TOP_POSTS} posts",
        "bottom_posts": f"Bottom {TOP_POSTS} posts",
        "most_commented_posts": f"Top {TOP_POSTS} posts by number of comments",
        "worst_post_per_star_tier": (
            f"Worst post of each author star tier below {STAR_TIER_LIMIT}"
        ),
        "most_prolific_authors": f"{TOP_AUTHORS} authors with the most posts",
        "biggest_absolute_authors": (
            f"{TOP_AUTHORS} authors with the biggest absolute score "
            "(downvotes counted as loudly as upvotes)"
        ),
        "most_downvoted_authors": f"{TOP_AUTHORS} authors with the heaviest downvoted total",
        "best_comments": f"{TOP_COMMENTS} highest-rated comments",
        "worst_comments": f"{TOP_COMMENTS} lowest-rated comments",
        "most_direct_replies": f"{TOP_COMMENTS} most directly answered comments",
        "most_total_replies": f"{TOP_COMMENTS} comments with the biggest thread below them",
        "by": "by",
        "rating": "rating",
        "stars": ("star", "stars"),
        "direct_replies": ("direct reply", "direct replies"),
        "comments": ("comment", "comments"),
        "posts": ("post", "posts"),
        "author_totals": "total {total}, {absolute} in absolute terms, {negative} downvoted",
        "replies_tail": "{total} in the whole thread",
        "empty_no_posts": "(no posts in this run)",
        "empty_no_comments": (
            "(comment statistics were not collected — re-run with --comment-stats)"
        ),
        "no_title": "(no text — image or video post)",
    },
    "ru": {
        "document_title": "ЧЕМПИОНЫ",
        "tag": "Тег",
        "period": "Период",
        "generated_from": "Постов / комментариев",
        "top_posts": f"Топ-{TOP_POSTS} постов",
        "bottom_posts": f"Худшие {TOP_POSTS} постов",
        "most_commented_posts": f"Топ-{TOP_POSTS} постов по числу комментариев",
        "worst_post_per_star_tier": (
            f"Худший пост в каждой звёздной группе авторов ниже {STAR_TIER_LIMIT}"
        ),
        "most_prolific_authors": f"{TOP_AUTHORS} автора с наибольшим числом постов",
        "biggest_absolute_authors": (
            f"{TOP_AUTHORS} автора с наибольшим рейтингом по модулю "
            "(минусы считаются наравне с плюсами)"
        ),
        "most_downvoted_authors": f"{TOP_AUTHORS} автора с самой тяжёлой суммой минусов",
        "best_comments": f"{TOP_COMMENTS} комментария с самым высоким рейтингом",
        "worst_comments": f"{TOP_COMMENTS} комментария с самым низким рейтингом",
        "most_direct_replies": f"{TOP_COMMENTS} комментария с наибольшим числом прямых ответов",
        "most_total_replies": f"{TOP_COMMENTS} комментария с самой большой веткой под ними",
        "by": "автор",
        "rating": "рейтинг",
        "stars": ("звезда", "звезды", "звёзд"),
        "direct_replies": ("прямой ответ", "прямых ответа", "прямых ответов"),
        "comments": ("комментарий", "комментария", "комментариев"),
        "posts": ("пост", "поста", "постов"),
        "author_totals": "всего {total}, по модулю {absolute}, минусы {negative}",
        "replies_tail": "{total} во всей ветке",
        "empty_no_posts": "(в этом запуске нет постов)",
        "empty_no_comments": (
            "(статистика по комментариям не собиралась — запустите с --comment-stats)"
        ),
        "no_title": "(без текста — картинка или видео)",
    },
}


def build_champions(
    posts: Sequence[Post],
    comments: Sequence[Comment],
    *,
    comments_collected: bool | None = None,
) -> list[Chapter]:
    """Pick the standouts out of one run's posts and comments.

    ``comments_collected`` separates "we looked and found nothing" from "we
    never looked", which are worth saying differently in the output. It is
    inferred from ``comments`` when not given.
    """
    if comments_collected is None:
        comments_collected = bool(comments)

    empty_comments = None if comments_collected else "empty_no_comments"
    return [
        _chapter("top_posts", _best_posts(posts), "empty_no_posts"),
        _chapter("bottom_posts", _worst_posts(posts), "empty_no_posts"),
        _chapter("most_commented_posts", _most_commented(posts), "empty_no_posts"),
        _chapter(
            "worst_post_per_star_tier", _worst_post_per_tier(posts), "empty_no_posts"
        ),
        _chapter("most_prolific_authors", _most_prolific(posts), "empty_no_posts"),
        _chapter("biggest_absolute_authors", _biggest_absolute(posts), "empty_no_posts"),
        _chapter("most_downvoted_authors", _most_downvoted(posts), "empty_no_posts"),
        _chapter("best_comments", _best_comments(comments), empty_comments),
        _chapter("worst_comments", _worst_comments(comments), empty_comments),
        _chapter("most_direct_replies", _most_direct(comments), empty_comments),
        _chapter("most_total_replies", _most_total(comments), empty_comments),
    ]


def _chapter(key: str, entries: list[Champion], empty_reason: str | None) -> Chapter:
    return Chapter(
        key=key,
        entries=tuple(entries),
        empty_reason=None if entries else empty_reason,
    )


def _best_posts(posts: Sequence[Post]) -> list[Champion]:
    ranked = sorted(posts, key=lambda post: (-post.score, post.id))
    return [_post_champion(post) for post in ranked[:TOP_POSTS]]


def _worst_posts(posts: Sequence[Post]) -> list[Champion]:
    ranked = sorted(posts, key=lambda post: (post.score, post.id))
    return [_post_champion(post) for post in ranked[:TOP_POSTS]]


def _most_commented(posts: Sequence[Post]) -> list[Champion]:
    """The posts that got people talking, whatever the vote said about them."""
    ranked = sorted(posts, key=lambda post: (-post.comments, post.id))
    return [
        _post_champion(post, with_comments=True)
        for post in ranked[:TOP_POSTS]
        if post.comments
    ]


def _worst_post_per_tier(posts: Sequence[Post]) -> list[Champion]:
    """The lowest-scoring post of every author star tier that appears at all.

    Tiers with no posts are simply absent — an empty line for each missing tier
    would say nothing.
    """
    worst_by_tier: dict[int, Post] = {}
    for post in posts:
        tier = post.author_stars
        if tier >= STAR_TIER_LIMIT:
            continue
        current = worst_by_tier.get(tier)
        if current is None or (post.score, post.id) < (current.score, current.id):
            worst_by_tier[tier] = post
    return [_post_champion(worst_by_tier[tier]) for tier in sorted(worst_by_tier)]


def _most_prolific(posts: Sequence[Post]) -> list[Champion]:
    ranked = _authors(posts, key=lambda entry: (-entry[0].posts, entry[0].author.casefold()))
    return [_author_champion(*entry) for entry in ranked[:TOP_AUTHORS]]


def _biggest_absolute(posts: Sequence[Post]) -> list[Champion]:
    """Loudest by volume: an author dragged to -200 counts as far as one praised to +200."""
    ranked = _authors(posts, key=lambda entry: (-entry[1], entry[0].author.casefold()))
    return [_author_champion(*entry) for entry in ranked[:TOP_AUTHORS]]


def _most_downvoted(posts: Sequence[Post]) -> list[Champion]:
    """The heaviest pile of dislikes, so the most negative sum comes first."""
    ranked = _authors(
        posts, key=lambda entry: (entry[0].score_negative_sum, entry[0].author.casefold())
    )
    return [
        _author_champion(*entry)
        for entry in ranked[:TOP_AUTHORS]
        if entry[0].score_negative_sum < 0
    ]


def _authors(posts: Sequence[Post], *, key: Any) -> list[tuple[Any, float]]:
    """Author summaries paired with their absolute score total, sorted by ``key``.

    The absolute total lives here rather than in :class:`AuthorSummary` because
    only the champions care about it, and the CSV columns are a promise to
    whoever reads them.
    """
    absolute: dict[str, float] = {}
    for post in posts:
        absolute[post.author] = absolute.get(post.author, 0.0) + abs(post.score)

    paired = [
        (summary, absolute.get(summary.author, 0.0))
        for summary in summarize_by_author(posts)
    ]
    return sorted(paired, key=key)


def _author_champion(summary: Any, absolute: float) -> Champion:
    return Champion(
        kind="author",
        title=summary.author,
        url=f"{SITE_URL}/user/{quote(summary.author)}",
        score=summary.score_sum,
        author=summary.author,
        author_rating=summary.author_rating,
        posts=summary.posts,
        score_abs_sum=absolute,
        score_negative_sum=summary.score_negative_sum,
    )


def _best_comments(comments: Sequence[Comment]) -> list[Champion]:
    ranked = sorted(comments, key=lambda item: (-item.score, item.id))
    return [_comment_champion(item) for item in ranked[:TOP_COMMENTS]]


def _worst_comments(comments: Sequence[Comment]) -> list[Champion]:
    ranked = sorted(comments, key=lambda item: (item.score, item.id))
    return [_comment_champion(item) for item in ranked[:TOP_COMMENTS]]


def _most_direct(comments: Sequence[Comment]) -> list[Champion]:
    ranked = sorted(
        comments, key=lambda item: (-item.direct_replies, -item.total_replies, item.id)
    )
    return [_comment_champion(item) for item in ranked[:TOP_COMMENTS] if item.direct_replies]


def _most_total(comments: Sequence[Comment]) -> list[Champion]:
    ranked = sorted(
        comments, key=lambda item: (-item.total_replies, -item.direct_replies, item.id)
    )
    return [_comment_champion(item) for item in ranked[:TOP_COMMENTS] if item.total_replies]


def _post_champion(post: Post, *, with_comments: bool = False) -> Champion:
    return Champion(
        kind="post",
        title=post.title,
        url=post.url,
        score=post.score,
        author=post.author,
        author_rating=post.author_rating,
        comments=post.comments if with_comments else None,
    )


def _comment_champion(comment: Comment) -> Champion:
    return Champion(
        kind="comment",
        title=comment.text,
        url=comment.url,
        score=comment.score,
        author=comment.author,
        author_rating=comment.author_rating,
        direct_replies=comment.direct_replies,
        total_replies=comment.total_replies,
    )


def write_champions_json(
    chapters: Sequence[Chapter], path: Path, *, meta: dict[str, Any] | None = None
) -> None:
    """The same chapters as data, with both languages' titles alongside."""
    document = {
        "meta": meta or {},
        "chapters": [
            {
                "key": chapter.key,
                "title": LABELS["en"][chapter.key],
                "title_ru": LABELS["ru"][chapter.key],
                "empty_reason": chapter.empty_reason,
                "entries": [_entry_row(entry) for entry in chapter.entries],
            }
            for chapter in chapters
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_champions_text(
    chapters: Sequence[Chapter],
    path: Path,
    *,
    language: str = "en",
    meta: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_champions(chapters, language=language, meta=meta), encoding="utf-8"
    )


def render_champions(
    chapters: Sequence[Chapter],
    *,
    language: str = "en",
    meta: dict[str, Any] | None = None,
) -> str:
    """The chapters as a plain-text document in one language."""
    words = LABELS[language]
    lines = [words["document_title"], "=" * len(words["document_title"])]
    lines.extend(_header_lines(meta or {}, words))

    for number, chapter in enumerate(chapters, start=1):
        title = f"{number}. {words[chapter.key]}"
        lines.extend(["", title, "-" * len(title)])
        if not chapter.entries:
            lines.append(words[chapter.empty_reason or "empty_no_posts"])
            continue
        for place, entry in enumerate(chapter.entries, start=1):
            lines.extend(_entry_lines(place, entry, words, language))
    return "\n".join(lines) + "\n"


def _header_lines(meta: dict[str, Any], words: dict[str, Any]) -> list[str]:
    lines = []
    if meta.get("tag"):
        lines.append(f"{words['tag']}: {meta['tag']}")
    if meta.get("start") and meta.get("end"):
        lines.append(f"{words['period']}: {meta['start']} … {meta['end']}")
    if meta.get("posts") is not None:
        lines.append(
            f"{words['generated_from']}: {meta['posts']} / {meta.get('comments', 0)}"
        )
    return lines


def _entry_lines(
    place: int, entry: Champion, words: dict[str, Any], language: str
) -> list[str]:
    indent = " " * 6
    stars = plural(entry.author_stars, words["stars"], language)
    who = (
        f"{entry.author_stars} {stars} "
        f"({words['rating']} {whole_rating(entry.author_rating)})"
    )

    if entry.kind == "author":
        # The author is the subject of these chapters, so they lead the entry
        # and their totals follow; there is no single instance to headline.
        lines = [f"{place:>3}. {entry.author}  {who}"]
    else:
        lines = [
            f"{place:>3}. {entry.score:+.2f}  {entry.title or words['no_title']}",
            f"{indent}{words['by']} {entry.author}  {who}",
        ]

    if entry.posts is not None:
        posts = plural(entry.posts, words["posts"], language)
        # A zero total means "nothing on that side at all", so it prints
        # unsigned here exactly as it does in the author table.
        totals = words["author_totals"].format(
            total=format_side_total(entry.score),
            absolute=f"{entry.score_abs_sum:.2f}",
            negative=format_side_total(entry.score_negative_sum),
        )
        lines.append(f"{indent}{entry.posts} {posts}, {totals}")
    if entry.comments is not None:
        counted = plural(entry.comments, words["comments"], language)
        lines.append(f"{indent}{entry.comments} {counted}")
    if entry.direct_replies is not None:
        replies = plural(entry.direct_replies, words["direct_replies"], language)
        tail = words["replies_tail"].format(total=entry.total_replies)
        lines.append(f"{indent}{entry.direct_replies} {replies}, {tail}")
    lines.append(f"{indent}{entry.url}")
    return lines


def whole_rating(rating: float) -> int:
    """A rating rounded to a whole number, always away from a .5 tie upwards.

    ``format`` would round a tie to the nearest even number instead, which made
    the same rating print as 4515 from a live run and 4514 when rebuilt from a
    report — the report stores two decimals, which is exactly what lands a value
    like 4514.5004 on the tie. Rounding one way always keeps the two agreeing.
    """
    return math.floor(rating + 0.5)


def plural(count: int, forms: Sequence[str], language: str) -> str:
    """Pick the right form of a counted noun.

    English needs two forms, Russian three and by its own rule — 1 звезда,
    2 звезды, 5 звёзд, with the teens all taking the last form. Getting this
    wrong is the sort of thing that makes a report read like a machine wrote it.
    """
    if language != "ru":
        return forms[0] if count == 1 else forms[1]

    last_two = abs(count) % 100
    last = abs(count) % 10
    if 11 <= last_two <= 14:
        return forms[2]
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def _entry_row(entry: Champion) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": entry.kind,
        "title": entry.title,
        "url": entry.url,
        "score": round(entry.score, 3),
        "author": entry.author,
        "author_rating": round(entry.author_rating, 2),
        "author_stars": entry.author_stars,
    }
    if entry.posts is not None:
        row["posts"] = entry.posts
        row["score_abs_sum"] = round(entry.score_abs_sum, 3)
        row["score_negative_sum"] = round(entry.score_negative_sum, 3)
    if entry.comments is not None:
        row["comments"] = entry.comments
    if entry.direct_replies is not None:
        row["direct_replies"] = entry.direct_replies
        row["total_replies"] = entry.total_replies
    return row


def load_report(path: Path) -> tuple[list[Post], list[Comment], dict[str, Any]]:
    """Read back a ``report.json`` written by a previous run.

    This is what lets the champions pass run as a separate command: everything
    it needs is already in that file, so regenerating costs no requests.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "posts" not in document:
        raise ValueError(f"{path} does not look like a joy-stats report")

    posts = [_post_from_row(row) for row in document.get("posts") or ()]
    comments = [_comment_from_row(row) for row in document.get("comments") or ()]
    return posts, comments, document.get("meta") or {}


def _post_from_row(row: dict[str, Any]) -> Post:
    return Post(
        id=int(row["id"]),
        url=row["url"],
        author=row["author"],
        author_rating=float(row.get("author_rating") or 0.0),
        title=row.get("title") or "",
        score=float(row.get("score") or 0.0),
        score_general=float(row.get("score_general") or 0.0),
        comments=int(row.get("comments") or 0),
        created_at=datetime.fromisoformat(row["created_at"]),
        nsfw=bool(row.get("nsfw")),
        banned=bool(row.get("banned")),
    )


def _comment_from_row(row: dict[str, Any]) -> Comment:
    return Comment(
        id=int(row["id"]),
        author=row["author"],
        score=float(row.get("score") or 0.0),
        parent_id=row.get("parent_id"),
        post_id=int(row.get("post_id") or 0),
        text=row.get("text") or "",
        author_rating=float(row.get("author_rating") or 0.0),
        direct_replies=int(row.get("direct_replies") or 0),
        total_replies=int(row.get("total_replies") or 0),
    )


def champion_files(out_dir: Path) -> dict[str, Path]:
    """The three files this pass writes, so callers agree on the names."""
    return {
        "json": out_dir / "champions.json",
        "en": out_dir / "champions.txt",
        "ru": out_dir / "champions-ru.txt",
    }


def write_all(
    chapters: Sequence[Chapter],
    out_dir: Path,
    *,
    meta: dict[str, Any] | None = None,
) -> list[Path]:
    """Write the JSON and both text renderings; returns the paths written."""
    paths = champion_files(out_dir)
    write_champions_json(chapters, paths["json"], meta=meta)
    write_champions_text(chapters, paths["en"], language="en", meta=meta)
    write_champions_text(chapters, paths["ru"], language="ru", meta=meta)
    return [paths["json"], paths["en"], paths["ru"]]


def comment_rows(comments: Iterable[Comment]) -> list[dict[str, Any]]:
    """Comments in the shape ``report.json`` stores them."""
    return [
        {
            "id": comment.id,
            "post_id": comment.post_id,
            "parent_id": comment.parent_id,
            "author": comment.author,
            "author_rating": round(comment.author_rating, 2),
            "author_stars": comment.author_stars,
            "score": round(comment.score, 3),
            "text": comment.text,
            "direct_replies": comment.direct_replies,
            "total_replies": comment.total_replies,
        }
        for comment in comments
    ]
