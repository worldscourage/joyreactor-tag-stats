"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import math
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__, config
from .client import GraphQLClient, JoyreactorError
from .exporters import (
    format_authors_table,
    format_comment_highlights,
    format_posts_table,
    write_authors_csv,
    write_json,
    write_posts_csv,
)
from .models import Post
from .scraper import TagScraper, parse_tag_url
from .stats import AUTHOR_SORT_KEYS, overall_totals, summarize_by_author
from .text import COMMON_TAG_SHARE, fill_missing_titles

logger = logging.getLogger("joyreactor_stats")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="joy-stats",
        description=(
            "Collect joyreactor.cc posts of one tag within a date range and "
            "summarise the scores per author."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  joy-stats --start 2025-08-01 --end 2025-09-01\n'
            '  joy-stats --tag "Бенефис кринжа" --start 2024-08-23 --end 2024-09-01 '
            "--out-dir reports\n"
            "  joy-stats --url "
            "'https://joyreactor.cc/tag/%D0%91%D0%B5%D0%BD%D0%B5%D1%84%D0%B8%D1%81"
            "%20%D0%BA%D1%80%D0%B8%D0%BD%D0%B6%D0%B0/all' --last-days 30\n"
        ),
    )

    target = parser.add_argument_group("what to scrape")
    target.add_argument(
        "--tag",
        default=None,
        help=f"Tag name, decoded (default: {config.DEFAULT_TAG!r}).",
    )
    target.add_argument(
        "--url",
        default=None,
        help="Tag URL copied from the browser; the tag and line type are taken from it.",
    )
    target.add_argument(
        "--line-type",
        default=None,
        choices=sorted(set(config.LINE_TYPES.values())),
        help="Which line of the tag to read (default: ALL).",
    )

    period = parser.add_argument_group("date range (site time, Europe/Moscow)")
    period.add_argument(
        "--start",
        type=parse_datetime,
        help="Oldest post to include, e.g. 2025-08-01 or '2025-08-01 12:30'.",
    )
    period.add_argument(
        "--end",
        type=parse_datetime,
        help="Newest post to include (inclusive). Defaults to now.",
    )
    period.add_argument(
        "--last-days",
        type=int,
        help="Shorthand for --start (now - N days). Ignored when --start is given.",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "--out-dir",
        type=Path,
        help="Write posts.csv, authors.csv and report.json into this directory.",
    )
    output.add_argument("--posts-csv", type=Path, help="Write the post rows here.")
    output.add_argument("--authors-csv", type=Path, help="Write the author rows here.")
    output.add_argument("--json", type=Path, help="Write one combined JSON report here.")
    output.add_argument(
        "--sort-authors-by",
        default="score_sum",
        choices=AUTHOR_SORT_KEYS,
        help="Author table ordering (default: score_sum).",
    )
    output.add_argument(
        "--common-tag-share",
        type=share,
        default=COMMON_TAG_SHARE,
        metavar="FRACTION",
        help=(
            "Posts with no text get a title built from their tags; tags carried by "
            f"more than this share of the selection are left out (default: {COMMON_TAG_SHARE}). "
            "Use 1 to keep every tag."
        ),
    )
    output.add_argument(
        "--comment-stats",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Collect the best / worst / most-answered comment of each post. "
            "Costs one extra request per post with comments. When neither this "
            "flag nor --no-comment-stats is given, you are asked once the posts "
            "are known and the cost can be stated."
        ),
    )
    output.add_argument(
        "--show-posts",
        type=int,
        default=15,
        metavar="N",
        help="How many posts to print to the console; 0 hides the post table.",
    )
    output.add_argument("--quiet", action="store_true", help="Only print the tables.")

    tuning = parser.add_argument_group("crawler tuning")
    tuning.add_argument(
        "--delay",
        type=float,
        default=config.REQUEST_DELAY_SECONDS,
        help=f"Seconds to wait between requests (default: {config.REQUEST_DELAY_SECONDS}).",
    )
    tuning.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Safety cap on total API requests (listing pages and comment fetches).",
    )
    tuning.add_argument(
        "--endpoint",
        default=config.GRAPHQL_URL,
        help="Override the GraphQL endpoint (useful for testing).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def share(raw: str) -> float:
    """A fraction in (0, 1], for --common-tag-share."""
    try:
        value = float(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a number") from error
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(
            f"share must be greater than 0 and at most 1, got {value}"
        )
    return value


def parse_datetime(raw: str) -> datetime:
    """Parse a date or datetime; naive values are read as site (Moscow) time."""
    try:
        value = datetime.fromisoformat(raw.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Cannot read {raw!r} as a date. Use 2025-08-01 or '2025-08-01 12:30'."
        ) from error
    if value.tzinfo is None:
        value = value.replace(tzinfo=config.SITE_TIMEZONE)
    return value


def resolve_period(args: argparse.Namespace) -> tuple[datetime, datetime]:
    end = args.end or datetime.now(tz=config.SITE_TIMEZONE)
    if args.start:
        start = args.start
    elif args.last_days is not None:
        start = end - timedelta(days=args.last_days)
    else:
        raise SystemExit("Give a period: use --start (with optional --end) or --last-days.")
    if start > end:
        raise SystemExit("--start must not be later than --end.")
    return start, end


def resolve_target(args: argparse.Namespace) -> tuple[str, str]:
    """Figure out which tag and line type to read from the mix of options."""
    tag, line_type = config.DEFAULT_TAG, "ALL"
    if args.url:
        tag, line_type = parse_tag_url(args.url)
    if args.tag:
        tag = args.tag
    if args.line_type:
        line_type = args.line_type
    return tag, line_type


def prompt_yes_no(
    question: str,
    *,
    default: bool,
    ask: Callable[[str], str] = input,
) -> bool:
    """Ask a yes/no question until the answer is understood."""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = ask(f"{question} {suffix} ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt:
            raise SystemExit("\nCancelled.") from None

        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def describe_comment_cost(post_count: int, delay: float) -> str:
    """A one-line estimate of what reading that many comment threads costs."""
    # Rounded up: an estimate that reads "0 s" or undersells the wait is worse
    # than one that is a moment pessimistic.
    seconds = post_count * delay
    duration = (
        f"~{math.ceil(seconds)} s" if seconds < 90 else f"~{math.ceil(seconds / 60)} min"
    )
    return f"{post_count} request{'s' if post_count != 1 else ''}, {duration}"


def decide_comment_stats(
    args: argparse.Namespace,
    posts: Sequence[Post],
    *,
    interactive: bool | None = None,
    ask: Callable[[str], str] = input,
) -> bool:
    """Whether to read comment threads: the flag if given, otherwise ask.

    Asking here rather than up front means the question can state the real cost,
    which depends on how many of the collected posts actually have comments.
    """
    if args.comment_stats is not None:
        return args.comment_stats

    with_comments = sum(1 for post in posts if post.comments)
    if not with_comments:
        return False  # Nothing to fetch, so nothing worth asking about.

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        logger.warning(
            "Skipping comment statistics: no terminal to ask on. Pass "
            "--comment-stats or --no-comment-stats to choose explicitly."
        )
        return False

    cost = describe_comment_cost(with_comments, args.delay)
    print(
        f"\n{with_comments} of {len(posts)} collected posts have comments.\n"
        f"Reading their threads adds the best / worst / most-answered comment "
        f"columns and costs {cost}."
    )
    return prompt_yes_no("Collect comment statistics?", default=True, ask=ask)


def output_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    """--out-dir is a shorthand for the three explicit paths."""
    base = args.out_dir
    return {
        "posts_csv": args.posts_csv or (base / "posts.csv" if base else None),
        "authors_csv": args.authors_csv or (base / "authors.csv" if base else None),
        "json": args.json or (base / "report.json" if base else None),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        tag, line_type = resolve_target(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    start, end = resolve_period(args)

    logger.info(
        "Reading tag %r (%s line) from %s to %s",
        tag,
        line_type,
        start.isoformat(),
        end.isoformat(),
    )

    try:
        with GraphQLClient(args.endpoint, delay=args.delay) as client:
            scraper = TagScraper(client, max_requests=args.max_requests)
            posts = scraper.fetch_range(tag, start, end, line_type)
            collect_comments = decide_comment_stats(args, posts)
            if collect_comments:
                posts = scraper.attach_comment_stats(posts)
    except JoyreactorError as error:
        raise SystemExit(f"Could not read the tag: {error}") from error

    # Postprocess before anything is reported or written: a text-less post gets
    # a title from its tags, which can only be judged against the full selection.
    posts = fill_missing_titles(posts, common_tag_share=args.common_tag_share)

    authors = summarize_by_author(posts, sort_by=args.sort_authors_by)
    totals = overall_totals(posts)
    logger.info(
        "Collected %d posts by %d authors (tag holds %s posts in total)",
        totals["posts"],
        totals["authors"],
        scraper.total_posts_in_tag if scraper.total_posts_in_tag is not None else "?",
    )

    _print_report(args, tag, line_type, start, end, posts, authors, totals)
    _write_files(args, tag, line_type, start, end, posts, authors, totals)
    return 0


def _print_report(args, tag, line_type, start, end, posts, authors, totals) -> None:
    print(f"\nTag: {tag}  ({line_type} line)")
    print(f"Period: {start:%Y-%m-%d %H:%M} … {end:%Y-%m-%d %H:%M} (Europe/Moscow)")
    print(
        f"Posts: {totals['posts']}   Authors: {totals['authors']}   "
        f"Total score: {totals['score_sum']:+.2f}   Comments: {totals['comments_sum']}"
    )

    if not posts:
        print("\nNo posts in this period.")
        return

    if args.show_posts:
        print("\nPosts (newest first)")
        print(format_posts_table(posts, limit=args.show_posts))

    if any(post.comment_stats for post in posts) and args.show_posts:
        print("\nComment highlights")
        print(format_comment_highlights(posts, limit=args.show_posts))

    print("\nPer-author summary")
    print(format_authors_table(authors))


def _write_files(args, tag, line_type, start, end, posts, authors, totals) -> None:
    paths = output_paths(args)
    if paths["posts_csv"]:
        write_posts_csv(posts, paths["posts_csv"])
    if paths["authors_csv"]:
        write_authors_csv(authors, paths["authors_csv"])
    if paths["json"]:
        write_json(
            paths["json"],
            meta={
                "tag": tag,
                "line_type": line_type,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "generated_at": datetime.now(tz=config.SITE_TIMEZONE).isoformat(),
                "tool_version": __version__,
                "totals": totals,
            },
            posts=posts,
            authors=authors,
        )
    written = [str(path) for path in paths.values() if path]
    if written:
        print("\nWritten: " + ", ".join(written))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
