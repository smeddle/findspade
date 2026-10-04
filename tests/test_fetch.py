import random
from pathlib import Path

import pytest

from findspade.fetch import ERROR_PAGE_RETRIES, HumanPace, WrongLocationError, take_snapshot
from findspade.item_page import TITLE
from findspade.records import build_records
from findspade.search_page import SEARCH_PAGE_READY
from findspade.snapshot import Snapshot
from findspade.terms import search_url

FIXTURES = Path(__file__).parent / "fixtures"
VERIFY_PAGE = "<html><body><h1>Please verify you are a human</h1></body></html>"
ERROR_PAGE = (
    "<html><body><h1>SORRY</h1><p>Something went wrong on our end</p>"
    "<p>0.ad24c317.1791046358.2a76ec7b</p><p>Please go back and try again</p></body></html>"
)


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
        self.waited_for: dict[str, str | None] = {}  # url -> CSS selector awaited
        self.failures: dict[str, int] = {}  # url -> times to return a verification page first
        self.errors: dict[str, int] = {}  # url -> times to return eBay's error page first

    def get(self, url: str, wait_for: str | None = None) -> str:
        self.requested.append(url)
        self.waited_for[url] = wait_for
        if self.errors.get(url, 0) > 0:
            self.errors[url] -= 1
            return ERROR_PAGE
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


def interrupt(url, error):
    raise KeyboardInterrupt  # the user pressing Ctrl-C at the prompt


def run(snapshot, browser, terms=("Antiquity",), on_blocked=None, log=None, verbose=False):
    pauses = []
    take_snapshot(
        list(terms),
        snapshot,
        browser,
        pause=lambda: pauses.append(1),
        on_blocked=on_blocked or (lambda url, error: None),
        log=log or (lambda message: None),
        verbose=verbose,
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


def test_waits_for_results_or_item_title_but_not_for_descriptions(tmp_path):
    browser = FakeBrowser()

    run(Snapshot(tmp_path), browser)

    assert browser.waited_for[search_url("Antiquity", 1)] == SEARCH_PAGE_READY
    assert browser.waited_for["https://www.ebay.com/itm/307111434811"] == TITLE
    descriptions = [url for url in browser.requested if "ebaydesc" in url]
    assert descriptions and all(browser.waited_for[url] is None for url in descriptions)


def test_rerun_of_a_finished_snapshot_fetches_nothing(tmp_path):
    snapshot = Snapshot(tmp_path)
    run(snapshot, FakeBrowser())

    browser = FakeBrowser()
    run(snapshot, browser)

    assert browser.requested == []


def test_rerun_uses_saved_results_and_continues_from_missing_or_incomplete_items(tmp_path):
    snapshot = Snapshot(tmp_path)
    first = FakeBrowser()
    first.failures["https://www.ebay.com/itm/307111434811"] = 1  # 5th item: user stops here
    with pytest.raises(KeyboardInterrupt):
        run(snapshot, first, on_blocked=interrupt)
    # Simulate an interruption between the 4th item's page and its description.
    (tmp_path / "items/158320267063/description.html").unlink()

    browser = FakeBrowser()
    messages = []
    run(snapshot, browser, log=messages.append)

    assert not any("/sch/" in url for url in browser.requested)  # no search pages refetched
    assert "https://www.ebay.com/itm/327366761616" not in browser.requested  # 1st item: done
    assert "https://www.ebay.com/itm/158320267063" in browser.requested  # incomplete
    assert "https://www.ebay.com/itm/307111434811" in browser.requested  # not reached
    assert "3 of 13 items already saved" in messages
    assert len(build_records(snapshot)) == 13


def test_rerun_continues_an_unfinished_search_from_the_next_page(tmp_path):
    snapshot = Snapshot(tmp_path)
    page_1 = FakeBrowser().pages[search_url("Antiquity", 1)]
    snapshot.save_search_page("Antiquity", 1, search_url("Antiquity", 1), page_1)

    browser = FakeBrowser()
    run(snapshot, browser)

    searched = [url for url in browser.requested if "/sch/" in url]
    assert searched == [search_url("Antiquity", 2)]


def test_user_gets_one_chance_to_clear_a_verification_page(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    url = "https://www.ebay.com/itm/307111434811"
    browser.failures[url] = 1
    blocked = []

    run(snapshot, browser, on_blocked=lambda url, error: blocked.append(url))

    assert blocked == [url]
    assert snapshot.item_page("307111434811", "item") == browser.item_html


def test_failed_item_page_is_saved_for_diagnosis_and_verbose_logs_each_load(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    browser.failures["https://www.ebay.com/itm/307111434811"] = 1
    errors, messages = [], []

    run(snapshot, browser, on_blocked=lambda url, e: errors.append(str(e)), log=messages.append,
        verbose=True)  # fmt: skip

    [error] = errors
    assert "Page has no item title or number (page title None" in error
    [saved] = (tmp_path / "debug").glob("307111434811-*.html")
    assert saved.read_text() == VERIFY_PAGE
    assert f"page saved to {saved}" in error
    item_lines = [m for m in messages if m.startswith("  [307111434811]")]
    assert item_lines[0] == "  [307111434811] fetching because it has no saved pages"
    assert "title NO, item number NO" in item_lines[1]  # the verification page
    assert "title yes, item number yes, description link yes" in item_lines[2]  # the retry
    assert item_lines[3].startswith("  [307111434811] description: ")


def test_verbose_explains_why_a_saved_item_is_fetched_again(tmp_path):
    snapshot = Snapshot(tmp_path)
    run(snapshot, FakeBrowser())
    (tmp_path / "items/307111434811/description.html").unlink()
    messages = []

    run(snapshot, FakeBrowser(), log=messages.append, verbose=True)

    assert any(
        m.startswith("  [307111434811] fetching because its description isn't saved")
        and "description link yes" in m
        for m in messages
    )


def test_user_is_asked_again_while_the_page_is_still_blocked(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    url = "https://www.ebay.com/itm/307111434811"
    browser.failures[url] = 2
    blocked = []

    run(snapshot, browser, on_blocked=lambda url, error: blocked.append(url))

    assert blocked == [url, url]
    assert snapshot.item_page("307111434811", "item") == browser.item_html


def test_user_can_stop_at_the_prompt_without_the_blocked_page_being_saved(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    browser.failures["https://www.ebay.com/itm/307111434811"] = 1

    with pytest.raises(KeyboardInterrupt):
        run(snapshot, browser, on_blocked=interrupt)

    assert snapshot.item_page("307111434811", "item") is None


def test_ebay_error_page_is_reloaded_after_the_usual_pause(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    url = search_url("Antiquity", 1)
    browser.errors[url] = 2
    blocked = []

    pauses = run(snapshot, browser, on_blocked=lambda url, error: blocked.append(url))

    assert browser.requested.count(url) == 3
    assert pauses == len(browser.requested)  # every reload waited like any other page
    assert blocked == []  # no need to involve the user
    assert len(snapshot.searches()[0][1]) == 2


def test_persistent_ebay_error_page_is_handed_to_the_user_after_the_reloads(tmp_path):
    browser = FakeBrowser()
    url = search_url("Antiquity", 1)
    browser.errors[url] = 1 + ERROR_PAGE_RETRIES + 1  # still failing once the user is asked
    blocked = []

    run(Snapshot(tmp_path), browser, on_blocked=lambda url, error: blocked.append(url))

    assert blocked == [url, url]  # after the automatic reloads, and once more after Enter
    assert browser.requested.count(url) == 1 + ERROR_PAGE_RETRIES + 2


def test_catalogue_product_page_is_saved_without_a_description_or_asking_the_user(tmp_path):
    snapshot = Snapshot(tmp_path)
    browser = FakeBrowser()
    url = "https://www.ebay.com/itm/307111434811"
    browser.pages[url] = fixture("items/358862393122/item.html")
    blocked = []

    run(snapshot, browser, on_blocked=lambda url, error: blocked.append(url))

    assert blocked == []
    assert snapshot.item_page("307111434811", "item") == browser.pages[url]
    assert snapshot.item_page("307111434811", "description") is None

    rerun = FakeBrowser()
    run(snapshot, rerun)
    assert url not in rerun.requested


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
