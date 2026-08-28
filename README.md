# joyreactor-stats

Collect the posts of a single **joyreactor.cc** tag inside a date range, and summarise
the score each author collected.

Built for the tag `Бенефис кринжа`
([`/tag/%D0%91%D0%B5%D0%BD%D0%B5%D1%84%D0%B8%D1%81%20%D0%BA%D1%80%D0%B8%D0%BD%D0%B6%D0%B0/all`](https://joyreactor.cc/tag/%D0%91%D0%B5%D0%BD%D0%B5%D1%84%D0%B8%D1%81%20%D0%BA%D1%80%D0%B8%D0%BD%D0%B6%D0%B0/all)),
which is the default tag — but any tag works.

## What you get

**Per post:** author (with their site-wide rating and its star count), score (the users'
likes minus dislikes, as the site weighs them), number of comments, a title derived from
the post body, creation time, post URL, NSFW/banned flags.

Posts with no text of their own (a bare image or video) are titled from their tags
instead — see [Titles from tags](#titles-from-tags).

**Per post's comment thread:** the **best** comment (author + highest rating), the
**worst** comment (author + lowest rating), and the **most answered** comment (author +
direct replies + replies in its whole subtree, however deeply nested).

**Per author:** their rating and stars, number of posts, and the **MIN / MAX / SUM** (plus
average) of their post scores, along with the total comments their posts attracted and
their first/last post in the period.

Results are printed as tables and, optionally, written as `posts.csv`, `authors.csv` and a
combined `report.json`.

```
Tag: Бенефис кринжа  (ALL line)
Period: 2025-08-31 00:00 … 2025-09-01 00:00 (Europe/Moscow)
Posts: 34   Authors: 11   Total score: +585.28   Comments: 261

Per-author summary
Author         Stars         Rating  Posts     Min      Max      Sum      Avg  Comments
-------------  ------------  ------  -----  ------  -------  -------  -------  --------
Culexus        ★★★★             628     17   -5.00    +5.47   -58.96    -3.47        29
Haspen         ★★★★★★★         3170      4   -7.00   +58.57  +119.46   +29.86        40
a6pxZxz        ★×14           20620      2  +84.21  +147.75  +231.96  +115.98        38
...
```

## Installation

You need **Python 3.10 or newer**. The only runtime dependency is
[`requests`](https://pypi.org/project/requests/).

The commands below all do the same three things: install Python, create a virtual
environment in the project folder, and install this project into it.

### macOS

```bash
brew install python@3.12          # skip if you already have Python 3.10+
git clone <this-repo> && cd cringe-stats
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
git clone <this-repo> && cd cringe-stats
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Windows

Install Python from [python.org](https://www.python.org/downloads/windows/) (tick
*"Add python.exe to PATH"*) or with `winget install Python.Python.3.12`, then in
**PowerShell**:

```powershell
git clone <this-repo>; cd cringe-stats
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

If PowerShell refuses to run the activation script, allow it once for your user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

> **Cyrillic output on Windows:** the console handles UTF-8 best with
> `chcp 65001` (or use Windows Terminal). The CSV files are written with a BOM so that
> Excel shows Cyrillic author names correctly without any extra steps.

### Verify the installation

```bash
joy-stats --version
joy-stats --help
```

`joy-stats` and `python -m joyreactor_stats` are interchangeable — use the latter if the
script is not on your `PATH`.

## Usage

The default tag is `Бенефис кринжа`, so a period is the only thing you must supply:

```bash
# Everything posted in August 2025
joy-stats --start 2025-08-01 --end 2025-09-01

# The last 30 days, with files written to ./reports
joy-stats --last-days 30 --out-dir reports

# Another tag, taken straight from the browser address bar
joy-stats --url "https://joyreactor.cc/tag/anon/all" --start 2025-01-01 --end 2025-02-01

# A different tag by name, sorted by post count, no post table
joy-stats --tag "Бенефис кринжа" --start 2024-08-23 --end 2024-09-01 \
          --sort-authors-by posts --show-posts 0
```

### Options

| Option | Meaning |
| --- | --- |
| `--tag NAME` | Tag name, already decoded (default: `Бенефис кринжа`). |
| `--url URL` | Tag URL from the browser; the tag and line type are read from it. |
| `--line-type {ALL,NEW,GOOD,BEST}` | Which line of the tag to read (default: `ALL`). |
| `--start`, `--end` | Range bounds, inclusive. `2025-08-01` or `"2025-08-01 12:30"`. |
| `--last-days N` | Shorthand for `--start` = `--end` minus N days. |
| `--out-dir DIR` | Write `posts.csv`, `authors.csv`, `report.json` into `DIR`. |
| `--posts-csv`, `--authors-csv`, `--json` | Write individual files to exact paths. |
| `--sort-authors-by KEY` | `score_sum` (default), `score_max`, `score_min`, `score_avg`, `author_rating`, `posts`, `comments_sum`, `author`. |
| `--comment-stats` / `--no-comment-stats` | Collect the comment-thread columns, or skip them. With neither, you are asked. |
| `--common-tag-share F` | Share above which a tag counts as common and is left out of tag-derived titles (default `0.5`; `1` keeps every tag). |
| `--show-posts N` | Post rows to print (default 15; `0` prints none). |
| `--delay SECONDS` | Pause between requests (default 0.5). |
| `--max-requests N` | Hard cap on API calls, useful while experimenting. |
| `--quiet` | Suppress progress logging. |

### Dates and time zones

Joyreactor timestamps everything in **Moscow time (UTC+03:00)**, so a date without a time
zone is interpreted in that zone — `--start 2025-08-01` means midnight Moscow time, which
is what you see on the site. Add an offset if you prefer to be explicit:
`--start "2025-08-01T00:00:00+02:00"`.

### Exit codes

`0` on success. `1` (with a message on stderr) if the tag does not exist, the period is
invalid, or the site cannot be reached after retries.

## How it works

Joyreactor's own frontend is a Relay app talking to a public GraphQL endpoint at
`https://api.joyreactor.cc/graphql`. This project asks that endpoint the same question the
website asks — `tag(name:).postPager(type:).posts(offset:)` — which returns clean,
structured post data instead of HTML that would break on the next redesign.

The tag line comes back **newest first**, so a date range needs no full crawl: the scraper
pages backwards and stops the moment it walks past `--start`. Requests are throttled and
retried with a backoff, and overlapping pages are de-duplicated by post id.

| Module | Responsibility |
| --- | --- |
| `config.py` | Endpoint, time zone, and crawler defaults — the only place with site facts. |
| `client.py` | GraphQL transport: headers, throttling, retries, error translation. |
| `scraper.py` | Paging through a tag line, date-window logic, API rows → `Post`. |
| `comments.py` | Fetching a post's comment tree and reducing it to three highlights. |
| `text.py` | Deriving a title from a post's HTML body, or from its tags. |
| `rating.py` | The site's rating → stars thresholds, and nothing else. |
| `stats.py` | Per-author aggregation (min/max/sum/count) and run totals. |
| `exporters.py` | CSV, JSON, and plain-text table rendering. |
| `cli.py` | Argument parsing and wiring the pieces together. |

### A note on the `score` field

The site shows a weighted rating, which is a float and can be negative — `-14.922` is a
post that got dragged. It is stored as-is (rounded to three decimals in the exports); the
secondary `ratingGeneral` value the API returns is kept in `score_general` for reference.

### Author rating and stars

Each post carries its author's site-wide rating, so `author_rating` and `author_stars`
appear in both CSVs at no extra request — the listing query already returns them.

The rating is a float that grows with everything the user does on the site. The site turns
it into stars by counting how many thresholds it has passed: 20 rating earns the first
star, 50 the second, 150 the third, and so on, widening as it goes. `author_stars` uses
the site's own threshold table, so it equals what the profile page draws. A profile shows
them in rows of ten; we report the plain total, so a rating of 20 620 is `14`, not "one
full row and four".

Two caveats worth knowing:

- The rating is a **snapshot at scrape time**, not a value belonging to the post. Re-run
  the same date range next month and it will differ.
- In the per-author table the rating is taken from the author's **most recent** post in the
  window, which is the closest thing we have to their rating now.

In the console tables the stars are drawn as symbols while they fit (`★★★★`) and folded
into a count past ten (`★×14`), so a wide-rating run stays readable.

### Titles from tags

Joyreactor posts have no title field, so the first line of the body stands in for one. A
bare image or video post has no body either — and for those the tags describe the post
well, so they are used instead:

```
2025-08-31 14:32  Culexus  -5.00  0  Youtube brainrot, видео, без перевода
2025-08-31 14:11  Haspen  +27.07  10  Romahypax
```

Tags shared by **more than half** of the selected posts are left out, because they say
nothing about any individual post. In a real 34-post run over this tag, that dropped
`Бенефис кринжа` and `приколы для полных дегенератов` (both on 100% of posts) while
keeping `видео` — which sat on exactly 17 of 34, and exactly half is not more than half.

This runs as a postprocess pass over the finished selection, before anything is printed or
written, because "shared by most" can only be judged once every post is known. Change the
threshold with `--common-tag-share`, or set it to `1` to keep every tag. A post left with
no distinctive tags keeps an empty `title`, and the console shows
`(no text — image or video post)` for it.

### Comment-thread columns

`posts.csv` carries seven extra columns:

| Column | Meaning |
| --- | --- |
| `best_comment_author`, `best_comment_score` | The highest-rated comment in the thread. |
| `worst_comment_author`, `worst_comment_score` | The lowest-rated comment. |
| `most_replied_comment_author` | Author of the comment that drew the most discussion. |
| `most_replied_direct_replies` | Replies made straight to that comment. |
| `most_replied_total_replies` | Replies in its entire subtree, at any depth. |

The two counts differ more often than you would think: a comment with one reply that
started a 14-message argument beats a comment with three dead-end replies.

A post's whole thread arrives in **one request**, so this costs one extra request per post
that has comments — the slowest part of a large run. Ties go to the earlier comment, so
repeated runs agree.

Because that cost is easy to underestimate, **you are asked before it happens** unless you
said which you wanted. The question comes after the posts are collected, so it can state
the real price:

```
23 of 34 collected posts have comments.
Reading their threads adds the best / worst / most-answered comment columns and costs 23 requests, ~12 s.
Collect comment statistics? [Y/n]
```

Pressing Enter accepts. Pass `--comment-stats` or `--no-comment-stats` to decide up front
and never see the question — worth doing in scripts and cron jobs, because with no terminal
to ask on the run **skips** the comment pass and says so in a warning rather than hanging.
You are not asked when no collected post has comments, since there would be nothing to
fetch.

## Development

```bash
pip install -e ".[dev]"
pytest          # 123 tests, no network access required
ruff check .
```

The tests replace the GraphQL client with a fake that serves canned listing pages and
comment threads, including the overlapping-window quirk of the real API, so the suite is
fast and offline. The reply-counting tests cover deleted parents, cycles, and a
3000-deep thread.

## Being a good citizen

This tool reads public pages at a deliberately slow pace (one request per half second by
default) and sends no writes, votes, or comments. Please keep `--delay` sane, cache the
CSV/JSON output rather than re-crawling, and respect joyreactor's terms of use.

## License

[WTFPL](LICENSE) — Do What The Fuck You Want To Public License, version 2.
Do whatever you want with this code.
