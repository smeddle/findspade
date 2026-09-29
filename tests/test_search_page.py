from datetime import date
from pathlib import Path

import pytest

from findspade.search_page import (
    NotLoggedInError,
    SearchResult,
    UnexpectedPageError,
    parse_search_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "search"


def parse_fixture(name: str):
    return parse_search_page((FIXTURES / name).read_text(encoding="utf-8"))


def test_first_page_reads_every_field_of_a_result():
    page = parse_fixture("antiquity-p1.html")

    assert page.total_results == 67
    assert page.has_next_page
    assert page.results[0] == SearchResult(
        item_id="327366761616",
        url="https://www.ebay.com/itm/327366761616",
        title="Antiquity Board Game (Splotter Spellen) Third Edition With Wooden Box Organiser",
        subtitle="Pre-Owned",
        sold_date=date(2026, 9, 27),
        price="$106.04",
        shipping="+$6.61 delivery in 2-4 days",
        location="United Kingdom",
        seller="seller-1",
    )


def test_placeholder_cards_outside_the_results_list_are_ignored():
    # Each page carries two "Shop on eBay" cards with this listing id.
    for name in ["antiquity-p1.html", "antiquity-last.html", "zero-results.html"]:
        ids = [r.item_id for r in parse_fixture(name).results]
        assert "2500219655424533" not in ids


def test_last_page_has_no_next_page_and_tolerates_missing_shipping():
    page = parse_fixture("antiquity-last.html")

    assert not page.has_next_page
    assert len(page.results) == 8
    assert page.results[0].shipping is None
    assert page.results[0].price == "$145.67"


def test_middle_page_without_count_heading_or_subtitle():
    page = parse_fixture("metal-detecting-find-p2.html")

    assert page.total_results is None
    assert page.has_next_page
    coin = next(r for r in page.results if r.item_id == "257745509133")
    assert coin.subtitle is None
    assert coin.sold_date == date(2026, 9, 21)


def test_zero_results_page_is_empty_not_an_error():
    page = parse_fixture("zero-results.html")

    assert page.total_results == 0
    assert not page.has_next_page
    assert page.results == []


def test_sign_in_page_raises_not_logged_in():
    with pytest.raises(NotLoggedInError):
        parse_fixture("logged-out.html")


def test_unrecognised_page_raises():
    with pytest.raises(UnexpectedPageError):
        parse_search_page("<html><body><h1>Please verify you are a human</h1></body></html>")
