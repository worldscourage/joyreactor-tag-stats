"""Turning post HTML — or, failing that, post tags — into something usable as a title."""

from __future__ import annotations

import html
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

from .models import Post

#: The site stores media as placeholders inside the post body, e.g. a picture
#: becomes the literal text "&attribute_insert_1&". Those carry no meaning here.
_ATTRIBUTE_PLACEHOLDER = re.compile(r"&attribute_insert_\d+&")
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

DEFAULT_TITLE_LENGTH = 120


def derive_title(post_html: str | None, max_length: int = DEFAULT_TITLE_LENGTH) -> str:
    """Build a short single-line title out of a post's HTML body.

    Joyreactor posts have no title field, so the first line of the body is the
    closest honest equivalent. Image-only posts legitimately yield an empty
    string; callers decide how to display that.
    """
    if not post_html:
        return ""

    text = _ATTRIBUTE_PLACEHOLDER.sub(" ", post_html)
    # Give block-level tags a chance to act as word separators before stripping.
    text = re.sub(r"<(?:br|/p|/div|/h[1-6]|/li)\s*/?>", " ", text, flags=re.IGNORECASE)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _WHITESPACE.sub(" ", text).strip()

    return _truncate(text, max_length)


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


#: A tag on more than this share of the selected posts says nothing about an
#: individual post, so it is not worth showing as a title.
COMMON_TAG_SHARE = 0.5


def fill_missing_titles(
    posts: Sequence[Post],
    *,
    common_tag_share: float = COMMON_TAG_SHARE,
    max_length: int = DEFAULT_TITLE_LENGTH,
) -> list[Post]:
    """Give text-less posts a title built from their distinctive tags.

    Image-only posts have no text to derive a title from, but their tags usually
    describe them well — except for the tags shared by most of the selection
    (the scraped tag itself, and whatever always travels with it), which carry no
    information about any single post. Those are dropped.

    Runs over the whole selection because "shared by most" can only be judged
    once every post is known. Posts that already have a title are untouched, as
    are posts left with no distinctive tags.
    """
    posts = list(posts)
    if not posts:
        return posts

    common = _common_tags(posts, common_tag_share)
    filled = []
    for post in posts:
        if post.title:
            filled.append(post)
            continue
        distinctive = [tag for tag in post.tags if tag not in common]
        if not distinctive:
            filled.append(post)  # Nothing left worth saying.
            continue
        filled.append(replace(post, title=_truncate(", ".join(distinctive), max_length)))
    return filled


def _common_tags(posts: Sequence[Post], share: float) -> set[str]:
    """Tags carried by more than ``share`` of ``posts``.

    In a selection of one post every tag would be "common", which would throw
    away the only titles we could build, so the filter stands down there.
    """
    if len(posts) < 2:
        return set()

    counts = Counter(tag for post in posts for tag in set(post.tags))
    return {tag for tag, count in counts.items() if count > share * len(posts)}
