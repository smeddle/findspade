from datetime import date
from pathlib import Path

import pytest

from findspade.item_page import parse_item_page
from findspade.search_page import (
    BrowserCheckPage,
    EbayErrorPage,
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
        import_fees=None,
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


def test_us_delivery_location_shows_shipping_estimates_and_import_fees():
    page = parse_search_page(
        (FIXTURES.parent / "us" / "search" / "antiquity-p1.html").read_text(encoding="utf-8")
    )
    by_id = {r.item_id: r for r in page.results}

    assert by_id["327366761616"].shipping == "Shipping not specified"
    assert by_id["307111434811"].shipping == "+$23.38 shipping estimate"
    assert by_id["307111434811"].import_fees == "Import fees paid at checkout"
    # "delivery" in the import fees row must not overwrite the shipping cost.
    assert by_id["336404084470"].shipping == "+$4.90 delivery"
    assert by_id["336404084470"].import_fees == "Import fees due prior to delivery"


def test_zero_results_page_is_empty_not_an_error():
    page = parse_fixture("zero-results.html")

    assert page.total_results == 0
    assert not page.has_next_page
    assert page.results == []


def test_sign_in_page_raises_not_logged_in():
    with pytest.raises(NotLoggedInError):
        parse_fixture("logged-out.html")


def test_ebay_error_page_raises_its_own_error():
    html = "<html><body><h1>SORRY</h1><p>Something went wrong on our end</p></body></html>"
    with pytest.raises(EbayErrorPage):
        parse_search_page(html)
    with pytest.raises(EbayErrorPage):
        parse_item_page(html)


def test_error_wording_inside_scripts_is_ignored():
    script = "<script>var t = 'Something went wrong on our end';</script>"
    html = (FIXTURES / "antiquity-p1.html").read_text(encoding="utf-8")
    assert len(parse_search_page(html.replace("</body>", script + "</body>")).results) == 5


def test_ebay_browser_check_page_raises_its_own_error():
    html = (FIXTURES.parent / "browser-check.html").read_text(encoding="utf-8")
    with pytest.raises(BrowserCheckPage):
        parse_search_page(html)
    with pytest.raises(BrowserCheckPage):
        parse_item_page(html)


def test_unrecognised_page_raises():
    with pytest.raises(UnexpectedPageError):
        parse_search_page("<html><body><h1>Please verify you are a human</h1></body></html>")
