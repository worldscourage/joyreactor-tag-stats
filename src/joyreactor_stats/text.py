"""Turning post HTML into something usable as a title."""

from __future__ import annotations

import html
import re

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

    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"
