import random
from pathlib import Path

import pytest

from findspade.fetch import HumanPace, WrongLocationError, take_snapshot
from findspade.records import build_records
from findspade.search_page import UnexpectedPageError
from findspade.snapshot import Snapshot
from findspade.terms import search_url

FIXTURES = Path(__file__).parent / "fixtures"
VERIFY_PAGE = "<html><body><h1>Please verify you are a human</h1></body></html>"


def fixture(path: str, ship_to: str = "20002") -> str:
    html = (FIXTURES / path).read_text(encoding="utf-8")
    # The fixtures had the delivery location removed with the filter sidebar; put one back.
    location = (
        f'<button class="shipping-entry"><span class="zipcode-text">{ship_to}</span></button>'
    )
    return html.replace("<body>", "<body>" + location, 1)


class FakeBrowser:
    """Serves the "Antiquity" search fixtures; every item gets the same (US) item page."""

    def __init__(self, ship_to: str = "20002"):
        self.pages = {
            search_url("Antiquity", 1): fixture("search/antiquity-p1.html", ship_to),
            search_url("Antiquity", 2): fixture("search/antiquity-last.html", ship_to),
        }
        self.item_html = fixture("us/items/257745509133/item.html")
        self.description_html = fixture("items/257745509133/description.html")
        self.requested: list[str] = []
        self.failures: dict[str, int] = {}  # url -> times to return a verification page first

    def get(self, url: str) -> str:
        self.requested.append(url)
        if self.failures.get(url, 0) > 0:
            self.failures[url] -= 1
            return VERIFY_PAGE
        if url in self.pages:
            return self.pages[url]
        if url.startswith("https://www.ebay.com/itm/"):
            return self.item_html
        if url.startswith("https://itm.ebaydesc.com/"):
            return self.description_html
        raise AssertionError(f"Unexpected URL {url}")


def run(snapshot, browser, terms=("Antiquity",), on_blocked=None, log=None):
    pauses = []
    take_snapshot(
        list(terms),
        snapshot,
        browser,
        pause=lambda: pauses.append(1),
        on_blocked=on_blocked or (lambda url, error: None),
        log=log or (lambda message: None),
    )
    return len(pauses)


def test_fetches_every_search_page_then_every_item_with_a_pause_before_each(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()

    pauses = run(snapshot, browser)

    [(term, pages)] = snapshot.searches()
    assert term == "Antiquity" and len(pages) == 2
    assert snapshot.item_page("307111434811", "item") is not None
    assert snapshot.item_page("307111434811", "description") is not None
    assert len(build_records(snapshot)) == 13  # 5 on page 1, 8 on page 2
    assert pauses == len(browser.requested) == 2 + 13 * 2


def test_rerun_skips_items_already_fetched(tmp_path):
    snapshot = Snapshot(tmp_path)
    run(snapshot, FakeBrowser())

    browser = FakeBrowser()
    run(snapshot, browser)

    assert browser.requested == [search_url("Antiquity", 1), search_url("Antiquity", 2)]


def test_user_gets_one_chance_to_clear_a_verification_page(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    url = "https://www.ebay.com/itm/307111434811"
    browser.failures[url] = 1
    blocked = []

    run(snapshot, browser, on_blocked=lambda url, error: blocked.append(url))

    assert blocked == [url]
    assert snapshot.item_page("307111434811", "item") == browser.item_html


def test_second_verification_page_stops_the_run_without_saving_it(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    browser.failures["https://www.ebay.com/itm/307111434811"] = 2

    with pytest.raises(UnexpectedPageError):
        run(snapshot, browser)

    assert snapshot.item_page("307111434811", "item") is None


def test_refuses_to_run_unless_delivery_location_is_a_us_zip(tmp_path):
    snapshot = Snapshot(tmp_path)

    with pytest.raises(WrongLocationError, match="SE120HR"):
        run(snapshot, FakeBrowser(ship_to="SE120HR"))

    assert snapshot.searches() == []


def test_refuses_to_save_item_pages_showing_delivery_outside_the_us(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    browser.item_html = fixture("items/398366490754/item.html")  # delivery "to POSTCODE"

    with pytest.raises(WrongLocationError, match="POSTCODE"):
        run(snapshot, browser)

    assert snapshot.item_page("307111434811", "item") is None


def test_terms_differing_only_in_case_are_searched_once(tmp_path):
    browser = FakeBrowser()
    messages = []

    run(Snapshot(tmp_path), browser, terms=["Antiquity", "antiquity"], log=messages.append)

    assert browser.requested.count(search_url("Antiquity", 1)) == 1
    assert "Skipping 'antiquity': same search as an earlier term" in messages


def test_human_pace_waits_within_the_configured_ranges():
    waits = []
    pace = HumanPace(
        min_delay=4, max_delay=12, long_pause_chance=0.2, long_pause=(30, 90),
        sleep=waits.append, rng=random.Random(1),
    )  # fmt: skip

    for _ in range(200):
        pace()

    short = [w for w in waits if w < 30]
    assert all(4 <= w <= 12 for w in short)
    assert all(30 <= w <= 90 for w in waits if w >= 30)
    assert 20 < len(waits) - len(short) < 60  # about 20% long pauses
