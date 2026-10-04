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
from datetime import datetime
from pathlib import Path
from typing import Protocol

from bs4 import BeautifulSoup

from findspade.item_page import (
    DESCRIPTION_FRAME,
    ITEM_NUMBER,
    TITLE,
    ItemPage,
    ListingUnavailable,
    parse_item_page,
)
from findspade.search_page import (
    SEARCH_PAGE_READY,
    EbayErrorPage,
    UnexpectedPageError,
    parse_search_page,
)
from findspade.snapshot import Snapshot
from findspade.terms import search_url

MAX_PAGES_PER_TERM = 50  # a safety limit; eBay shows at most about 10,000 results
ERROR_PAGE_RETRIES = 3  # reloads after eBay's "Something went wrong" page before giving up
RECHECK_SECONDS = 3  # verbose: wait before re-reading an item page that failed to parse


class Browser(Protocol):
    def get(self, url: str, wait_for: str | None = None) -> str:
        """Load the URL and return its HTML, once the wait_for CSS selector matches."""


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
    verbose: bool = False,
) -> None:
    """With verbose, log the details of every item page load, to help diagnose failures."""
    fetcher = _Fetcher(snapshot, browser, pause, on_blocked, log, verbose)

    item_ids: list[str] = []
    for term in _unique_ignoring_case(terms, log):
        for item_id in fetcher.fetch_search(term):
            if item_id not in item_ids:
                item_ids.append(item_id)

    reasons = {i: reason for i in item_ids if (reason := _why_fetch(snapshot, i))}
    if len(reasons) < len(item_ids):
        log(f"{len(item_ids) - len(reasons)} of {len(item_ids)} items already saved")
    for n, (item_id, reason) in enumerate(reasons.items(), start=1):
        log(f"Item {n}/{len(reasons)}: {item_id}")
        fetcher.vlog(item_id, f"fetching because {reason}")
        fetcher.fetch_item(item_id)


@dataclass
class _Fetcher:
    snapshot: Snapshot
    browser: Browser
    pause: Callable[[], None]
    on_blocked: Callable[[str, Exception], None]
    log: Callable[[str], None]
    verbose: bool = False

    def vlog(self, item_id: str, message: str) -> None:
        if self.verbose:
            self.log(f"  [{item_id}] {message}")

    def fetch_search(self, term: str) -> list[str]:
        """Save every results page for the term and return the item ids found.

        Pages saved by an earlier run are reused rather than fetched again.
        """
        item_ids = []
        saved = 0  # how many pages, from page 1 with no gaps, an earlier run saved
        for page_number, html in self.snapshot.search_pages(term):
            if page_number != saved + 1:
                break  # a gap: fetch again from here
            saved = page_number
            page = parse_search_page(html)
            item_ids += [r.item_id for r in page.results]
            if not page.has_next_page:
                self.log(f"{term!r}: using {saved} saved results page(s)")
                return item_ids

        for page_number in range(saved + 1, MAX_PAGES_PER_TERM + 1):
            url = search_url(term, page_number)
            html, page = self._get(url, parse_search_page, wait_for=SEARCH_PAGE_READY)
            _check_us_location(page.ship_to)
            self.snapshot.save_search_page(term, page_number, url, html)
            item_ids += [r.item_id for r in page.results]
            self.log(f"{term!r} page {page_number}: {len(page.results)} results")
            if not page.has_next_page:
                break
        return item_ids

    def fetch_item(self, item_id: str) -> None:
        url = f"https://www.ebay.com/itm/{item_id}"
        html, item = self._get(url, lambda html: self._parse_item(item_id, html), wait_for=TITLE)
        if item is None:
            # Saved anyway, as a record of what eBay showed and so a rerun skips it.
            self.snapshot.save_item_page(item_id, "item", url, html)
            self.log(f"Item {item_id}: eBay showed a catalogue product page, not the listing")
            return
        _check_us_location(_delivery_destination(item.delivery))
        self.snapshot.save_item_page(item_id, "item", url, html)
        if item.description_url:
            # Plain seller HTML, served by eBay without a login, so there is nothing to check.
            self.pause()
            description = self.browser.get(item.description_url)
            self.vlog(item_id, f"description: {self._last_load()}, {len(description):,} chars")
            self.snapshot.save_item_page(item_id, "description", item.description_url, description)

    def _parse_item(self, item_id: str, html: str) -> ItemPage | None:
        """Parse a just-loaded item page, logging diagnostics and keeping pages that fail."""
        self.vlog(item_id, f"item page: {self._last_load()}, {_item_page_parts(html)}")
        try:
            return _parse_listing(html)
        except EbayErrorPage:
            raise
        except UnexpectedPageError as error:
            path = self._save_failed_page(item_id, html)
            if self.verbose and hasattr(self.browser, "html_now"):
                time.sleep(RECHECK_SECONDS)
                later = _item_page_parts(self.browser.html_now())
                self.vlog(item_id, f"same page {RECHECK_SECONDS} s later, not reloaded: {later}")
            raise type(error)(f"{error}; page saved to {path}") from error

    def _save_failed_page(self, item_id: str, html: str) -> Path:
        directory = self.snapshot.root / "debug"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{item_id}-{datetime.now():%H%M%S}.html"
        path.write_text(html, encoding="utf-8")
        return path

    def _last_load(self) -> str:
        load = getattr(self.browser, "last_load", None)
        if load is None:
            return "loaded"
        via = f"via {load.loaded_url}, " if load.loaded_url != load.final_url else ""
        ready = {None: "", True: ", content appeared", False: ", content NOT found in time"}
        return (
            f"HTTP {load.status} in {load.seconds} s, {via}from {load.final_url}"
            + ready[load.ready]
        )

    def _get(self, url: str, parse: Callable, wait_for: str | None = None):
        """Load and parse a page, pausing before every attempt.

        eBay's error page is reloaded up to ERROR_PAGE_RETRIES times. Any other unexpected
        page (e.g. verification) is handed to the user once; a second one stops the run.
        """
        retries = 0
        asked_user = False
        while True:
            self.pause()
            html = self.browser.get(url, wait_for=wait_for)
            try:
                return html, parse(html)
            except EbayErrorPage:
                if retries == ERROR_PAGE_RETRIES:
                    raise
                retries += 1
                self.log(f"eBay error page; reloading ({retries}/{ERROR_PAGE_RETRIES})")
            except UnexpectedPageError as error:
                if asked_user:
                    raise
                asked_user = True
                self.on_blocked(url, error)


def _parse_listing(html: str) -> ItemPage | None:
    """Parse an item page; None if eBay showed a catalogue product page instead."""
    try:
        return parse_item_page(html)
    except ListingUnavailable:
        return None


def _why_fetch(snapshot: Snapshot, item_id: str) -> str | None:
    """Why the item needs fetching, or None if an earlier run saved all of its pages."""
    if snapshot.item_page(item_id, "description") is not None:
        return None
    html = snapshot.item_page(item_id, "item")
    if html is None:
        return "it has no saved pages"
    if _parse_listing(html) is None:
        return None  # a catalogue product page, which has no description
    return f"its description isn't saved (saved item page: {_item_page_parts(html)})"


def _item_page_parts(html: str) -> str:
    """Which of the parts the parser needs are in an item page, e.g. for diagnostics."""
    soup = BeautifulSoup(html, "lxml")
    parts = {"title": TITLE, "item number": ITEM_NUMBER, "description link": DESCRIPTION_FRAME}
    found = ", ".join(
        f"{name} {'yes' if soup.select_one(sel) else 'NO'}" for name, sel in parts.items()
    )
    return f"{len(html):,} chars, {found}"


def _check_us_location(ship_to: str | None) -> None:
    if ship_to is not None and not re.fullmatch(r"\d{5}", ship_to):
        raise WrongLocationError(
            f"eBay's delivery location is {ship_to!r}, not a US ZIP code. "
            "Run `findspade login` and set it to a US ZIP via 'Shipping to' on a search page."
        )


def _delivery_destination(delivery: str | None) -> str | None:
    """'Estimated between Tue, Oct 13 and Tue, Oct 20 to 08075' -> '08075'"""
    match = delivery and re.search(r" to (.+)$", delivery)
    return match.group(1) if match else None


def _unique_ignoring_case(terms: list[str], log: Callable[[str], None]) -> list[str]:
    """eBay ignores case, so 'Roman coin' and 'roman coin' are the same search."""
    unique: list[str] = []
    for term in terms:
        if term.lower() in [u.lower() for u in unique]:
            log(f"Skipping {term!r}: same search as an earlier term")
        else:
            unique.append(term)
    return unique
