"""Fetch a snapshot: every results page for each search term, then each item's page and
description, at a human pace.

The browser is passed in (see browser.py for the real one), so this logic can be tested
without touching eBay. Every page is checked by its parser before it is saved, so a
sign-in or verification page is never stored as data.
"""

import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from findspade.item_page import parse_item_page
from findspade.search_page import UnexpectedPageError, parse_search_page
from findspade.snapshot import Snapshot
from findspade.terms import search_url

MAX_PAGES_PER_TERM = 50  # a safety limit; eBay shows at most about 10,000 results


class Browser(Protocol):
    def get(self, url: str) -> str:
        """Load the URL and return the page's HTML."""


class WrongLocationError(Exception):
    """eBay's delivery location isn't a US ZIP code, so shipping figures would be wrong."""


@dataclass
class HumanPace:
    """Random waits between page loads, with an occasional longer break."""

    min_delay: float = 4.0
    max_delay: float = 12.0
    long_pause_chance: float = 0.05
    long_pause: tuple[float, float] = (30.0, 90.0)
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)

    def __call__(self) -> None:
        if self.rng.random() < self.long_pause_chance:
            self.sleep(self.rng.uniform(*self.long_pause))
        else:
            self.sleep(self.rng.uniform(self.min_delay, self.max_delay))


def ask_user_to_unblock(url: str, error: Exception) -> None:
    """Default when eBay shows a sign-in or verification page: let the user deal with it."""
    input(f"\n{error}\nwhile loading {url}\nFix it in the browser window, then press Enter. ")


def take_snapshot(
    terms: list[str],
    snapshot: Snapshot,
    browser: Browser,
    pause: Callable[[], None],
    on_blocked: Callable[[str, Exception], None] = ask_user_to_unblock,
    log: Callable[[str], None] = print,
) -> None:
    fetcher = _Fetcher(snapshot, browser, pause, on_blocked, log)

    item_ids: list[str] = []
    for term in _unique_ignoring_case(terms, log):
        for item_id in fetcher.fetch_search(term):
            if item_id not in item_ids:
                item_ids.append(item_id)

    for n, item_id in enumerate(item_ids, start=1):
        if snapshot.item_page(item_id, "item") and snapshot.item_page(item_id, "description"):
            continue  # already fetched by an earlier, interrupted run
        log(f"Item {n}/{len(item_ids)}: {item_id}")
        fetcher.fetch_item(item_id)


@dataclass
class _Fetcher:
    snapshot: Snapshot
    browser: Browser
    pause: Callable[[], None]
    on_blocked: Callable[[str, Exception], None]
    log: Callable[[str], None]

    def fetch_search(self, term: str) -> list[str]:
        """Save every results page for the term and return the item ids found."""
        item_ids = []
        for page_number in range(1, MAX_PAGES_PER_TERM + 1):
            url = search_url(term, page_number)
            html, page = self._get(url, parse_search_page)
            _check_us_location(page.ship_to)
            self.snapshot.save_search_page(term, page_number, url, html)
            item_ids += [r.item_id for r in page.results]
            self.log(f"{term!r} page {page_number}: {len(page.results)} results")
            if not page.has_next_page:
                break
        return item_ids

    def fetch_item(self, item_id: str) -> None:
        url = f"https://www.ebay.com/itm/{item_id}"
        html, item = self._get(url, parse_item_page)
        self.snapshot.save_item_page(item_id, "item", url, html)
        if item.description_url:
            # Plain seller HTML, served by eBay without a login, so there is nothing to check.
            self.pause()
            description = self.browser.get(item.description_url)
            self.snapshot.save_item_page(item_id, "description", item.description_url, description)

    def _get(self, url: str, parse: Callable):
        """Load and parse a page, giving the user one chance to clear a block."""
        self.pause()
        html = self.browser.get(url)
        try:
            return html, parse(html)
        except UnexpectedPageError as error:
            self.on_blocked(url, error)
        html = self.browser.get(url)
        return html, parse(html)  # a second failure stops the run


def _check_us_location(ship_to: str | None) -> None:
    if ship_to is not None and not re.fullmatch(r"\d{5}", ship_to):
        raise WrongLocationError(
            f"eBay's delivery location is {ship_to!r}, not a US ZIP code. "
            "Run `findspade login` and set it to a US ZIP, e.g. 10001."
        )


def _unique_ignoring_case(terms: list[str], log: Callable[[str], None]) -> list[str]:
    """eBay ignores case, so 'Roman coin' and 'roman coin' are the same search."""
    unique: list[str] = []
    for term in terms:
        if term.lower() in [u.lower() for u in unique]:
            log(f"Skipping {term!r}: same search as an earlier term")
        else:
            unique.append(term)
    return unique
