import json
from pathlib import Path

import pytest

from findspade.cli import main
from findspade.records import build_records
from findspade.snapshot import Snapshot

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(path: str) -> str:
    return (FIXTURES / path).read_text(encoding="utf-8")


@pytest.fixture
def snapshot(tmp_path) -> Snapshot:
    """Two searches that both find the antiquity page-1 items, plus pages for two items."""
    snapshot = Snapshot(tmp_path)
    snapshot.save_search_page('"Antiquity"', 1, "https://e/a1", fixture("search/antiquity-p1.html"))
    snapshot.save_search_page("antiquity", 1, "https://e/b1", fixture("search/antiquity-p1.html"))
    snapshot.save_search_page(
        "metal detecting find", 2, "https://e/m2", fixture("search/metal-detecting-find-p2.html")
    )
    for item_id in ["307111434811", "257745509133"]:
        for kind in ["item", "description"]:
            html = fixture(f"items/{item_id}/{kind}.html")
            snapshot.save_item_page(item_id, kind, f"https://e/{item_id}/{kind}", html)
    return snapshot


def by_id(records: list[dict]) -> dict[str, dict]:
    return {r["item_id"]: r for r in records}


def test_one_record_per_item_listing_every_term_that_found_it(snapshot):
    records = build_records(snapshot)

    assert len(records) == 10  # 5 antiquity results (found twice) + 5 metal detecting results
    assert by_id(records)["307111434811"]["search_terms"] == ['"Antiquity"', "antiquity"]


def test_record_combines_search_result_item_page_and_description(snapshot):
    record = by_id(build_records(snapshot))["307111434811"]

    assert record["title"] == 'Roman Antiquity - A Roman " Trumpet " Fibula Brooch'
    assert record["sold_date"] == "2026-09-23"  # from the search card: has the year
    assert record["price_usd"] == "$33.14"  # from the search card
    assert record["price"] == "GBP 25.00"  # from the item page
    assert record["location"] == "Pontefract, United Kingdom"  # item page: includes the town
    assert record["category"] == [
        "Jewelry & Watches",
        "Vintage & Antique Jewelry",
        "Brooches & Pins",
    ]
    assert record["description"].startswith('This Roman antiquity "Trumpet" fibula brooch')


def test_details_are_found_in_item_specifics(snapshot):
    record = by_id(build_records(snapshot))["257745509133"]

    assert record["provenance"] == "Provenance: Roman"
    assert record["pas"] is None


def test_item_without_saved_pages_uses_its_search_result(snapshot):
    record = by_id(build_records(snapshot))["327366761616"]

    assert record["title"].startswith("Antiquity Board Game")
    assert record["location"] == "United Kingdom"
    assert record["shipping"] == "+$6.61 delivery in 2-4 days"
    assert record["price"] is None
    assert record["description"] is None


def test_unparseable_item_page_falls_back_to_search_result(snapshot, capsys):
    snapshot.save_item_page("327366761616", "item", "https://e", "<html>Please verify</html>")

    record = by_id(build_records(snapshot))["327366761616"]

    assert record["location"] == "United Kingdom"
    assert "327366761616" in capsys.readouterr().err


def test_catalogue_product_page_falls_back_to_search_result_quietly(snapshot, capsys):
    product_page = fixture("items/358862393122/item.html")
    snapshot.save_item_page("327366761616", "item", "https://e", product_page)

    record = by_id(build_records(snapshot))["327366761616"]

    assert record["location"] == "United Kingdom"
    assert capsys.readouterr().err == ""


def test_records_command_writes_jsonl(snapshot, capsys):
    main(["records", str(snapshot.root)])

    lines = (snapshot.root / "records.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    assert json.loads(lines[0])["item_id"]
    assert "Wrote 10 records" in capsys.readouterr().out
