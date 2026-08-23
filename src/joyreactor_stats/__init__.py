"""Scrape a joyreactor.cc tag line and summarise it per author."""

from __future__ import annotations

from .models import AuthorSummary, Post
from .scraper import TagScraper
from .stats import summarize_by_author

__all__ = ["AuthorSummary", "Post", "TagScraper", "summarize_by_author", "__version__"]

__version__ = "1.0.0"
