from pathlib import Path

import pytest

from findspade.item_page import parse_description, parse_item_page
from findspade.search_page import NotLoggedInError, UnexpectedPageError

FIXTURES = Path(__file__).parent / "fixtures"


def parse_item(item_id: str):
    return parse_item_page((FIXTURES / "items" / item_id / "item.html").read_text(encoding="utf-8"))


def test_auction_item_reads_every_field():
    item = parse_item("398366490754")

    assert item.item_id == "398366490754"
    assert item.title == (
        "Viking Omega/Pennanular Brooch 1100AD European Antiquity. Detecting Interest"
    )  # eBay splits "Pennanular" across two spans
    assert item.seller == "seller-1"
    assert item.sale_status == "Item sold on Sun, Sep 13 at 11:30 AM."
    assert item.price == "GBP 20.00"
    assert item.price_converted == "US $26.51"
    assert not item.best_offer_accepted
    assert item.condition == "Used"
    assert item.location == "Bromsgrove, United Kingdom"
    assert item.shipping == "GBP 2.27 (approx US $3.01) Standard Tracked Delivery"
    assert item.delivery == "Estimated between Fri, Oct 2 and Thu, Oct 8 to POSTCODE"
    assert item.category == [
        "Collectibles & Art",
        "Collectibles",
        "Decorative Collectibles",
        "Other Decorative Collectibles",
    ]
    assert item.category_id == "73467"
    assert item.description_url.startswith("https://itm.ebaydesc.com/itmdesc/398366490754?")


def test_item_specifics_use_full_text_of_truncated_values():
    specifics = parse_item("800639427458").item_specifics

    assert specifics["Metal Purity"] == "16carat"
    assert specifics["Condition"].startswith("Pre-owned - Excellent: This item")
    assert "..." not in specifics["Condition"]
    assert specifics["Condition"].endswith("described in the seller’s listing.")


def test_best_offer_and_free_shipping():
    item = parse_item("800639427458")

    assert item.best_offer_accepted
    assert item.price == "GBP 1,464.02"
    assert item.shipping == "Free Evri Tracked"


def test_item_without_breadcrumb_condition_or_shipping_row():
    coin = parse_item("257745509133")
    assert coin.category == []
    assert coin.category_id == "122472"  # still available from the description URL
    assert coin.condition is None
    assert coin.item_specifics["Historical Period"] == "Roman Imperial (235 - 476 AD)"

    brooch = parse_item("307111434811")
    assert brooch.shipping is None
    assert brooch.delivery == "Varies"
    assert brooch.location == "Pontefract, United Kingdom"


def test_description_keeps_line_breaks():
    html = (FIXTURES / "items" / "257745509133" / "description.html").read_text(encoding="utf-8")
    lines = parse_description(html).splitlines()

    assert lines[0] == "(POSTAGE DISCOUNTS TABLE) UK."
    assert "Large items tracked £4.30" in lines


def test_sign_in_page_raises_not_logged_in():
    html = (FIXTURES / "search" / "logged-out.html").read_text(encoding="utf-8")
    with pytest.raises(NotLoggedInError):
        parse_item_page(html)


def test_unrecognised_page_raises():
    with pytest.raises(UnexpectedPageError):
        parse_item_page("<html><body><h1>Please verify you are a human</h1></body></html>")
