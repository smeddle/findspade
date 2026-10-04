# findspade
Search online auctions for antiquities of UK provenance.

AI-coded. Do with it what thou wilt.

## Setup

Requires Python 3.11+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
```

Dependencies are declared in `pyproject.toml`: runtime ones under `dependencies`,
development tools (`pytest`, `ruff`) under the `dev` extra.

## Usage

Search terms come either from a comma-separated list or from a file with one term per line:

```sh
findspade urls --terms '"uk antiquity",roman coin'
findspade urls --terms-file terms.txt
```

Double quotes are passed through to eBay as part of the term, so `"uk antiquity"` searches for
the exact phrase while `roman coin` searches for both words. In `--terms`, a comma inside
double quotes does not split the term.

`urls` prints the eBay sold-items search URL for each term (UK sellers, available to the US,
used condition, 240 results per page).

### Taking a snapshot

First, once (and again whenever eBay logs you out):

```sh
findspade login
```

This opens a browser window: sign in to eBay, then close it. The login is kept in
`data/browser-profile/`, which holds your eBay cookies and is git-ignored.

Shipping figures depend on the delivery location. Search URLs set it to a US ZIP code
(`_stpos=08075`, in `terms.py`), and the snapshot stops if a search or item page shows
delivery to anywhere else; if that happens, run `findspade login` again and set "Shipping
to" a US ZIP on any search page.

Then:

```sh
findspade snapshot --terms-file terms.txt
```

This fetches every results page for each term, then each item's page and description,
waiting 4–12 seconds between pages (`--min-delay`, `--max-delay`) with an occasional
longer break, and finally writes `records.jsonl`. After each page loads it waits (up to
10 seconds) for the results or item title to appear, so eBay's automatic "Checking your
browser" bot check can clear by itself. eBay's occasional "Something went wrong
on our end" page is reloaded automatically (after the same wait), up to 3 times. For
anything it can't get past by itself (a sign-in or verification page, or a persistent error
page) it pauses: deal with it in the browser window if needed and press Enter to reload,
as often as it takes, or press Ctrl-C to stop. Items whose listing eBay says is missing ("Looks like
this page is missing") get a `MISSING` file in their directory instead of pages, and are
skipped from then on; their records come from the search results.

If a snapshot is interrupted, finish it with:

```sh
findspade resume data/snapshots/2026-10-04
```

This uses the search terms saved in the snapshot and its saved results pages (fetching
only the pages a search hadn't reached), then fetches only the items without an
`item.html` or `MISSING` file. (An item's description is saved before its item page, so a
saved item page means the item is complete.) Running the original `snapshot` command again on the same day does the same.

Both commands take `--verbose`, which logs a line per item page load (HTTP status, time,
final URL, and whether the title, item number and description link were found). Whenever an item page can't be parsed, the
page is saved under `debug/` in the snapshot for inspection.

### Snapshots and records

A snapshot is a directory of raw pages saved exactly as fetched, one per date, e.g.
`data/snapshots/2026-10-03/` (layout described in `src/findspade/snapshot.py`). Turn one
into `records.jsonl`, one JSON record per sold item, with:

```sh
findspade records data/snapshots/2026-10-03
```

Each record combines the item's search result, item page and description: title, sold
date, prices, condition, seller, location, shipping, category, item specifics, the full
description text, any PAS / export licence / provenance mentions, and the search terms
that found it. `item_page_status` says whether the item-page fields could be filled in:
`ok`, `listing_missing`, `product_page` (eBay showed a catalogue page instead of the
listing), `not_fetched` or `unreadable`; otherwise those fields come from the search
results or are empty. Records can be rebuilt from the raw pages at any time.

## Development

```sh
pytest
ruff check . && ruff format --check .
```

Scraped data (`data/`) and raw saved pages (`samples/`) are git-ignored.

### Test fixtures

`tests/fixtures/` holds trimmed, anonymised copies of saved eBay pages. Raw pages contain
the logged-in user's name, username and postcode, so never commit them directly; make a
fixture with:

```sh
python tools/trim_fixture.py samples/search/foo.html tests/fixtures/search/foo.html --max-results 5
python tools/trim_fixture.py samples/items/123/item.html tests/fixtures/items/123/item.html
python tools/trim_fixture.py samples/items/123/description.html \
    tests/fixtures/items/123/description.html --redact <seller username>
```

Seller usernames are found and replaced automatically on search and item pages; a
description page doesn't show the username, so pass it with `--redact`. Check the result
for anything personal before committing.
🅮 AI-coded. Do with it what thou wilt.
