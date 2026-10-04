import json

import pytest

from findspade.snapshot import Snapshot


def test_search_pages_are_kept_in_page_order_and_resaving_replaces(tmp_path):
    snapshot = Snapshot(tmp_path)
    snapshot.save_search_page('"roman coin"', 2, "https://e/2", "<p>two</p>", "2026-10-03T10:01:00")
    snapshot.save_search_page('"roman coin"', 1, "https://e/1", "<p>one</p>", "2026-10-03T10:00:00")
    snapshot.save_search_page('"roman coin"', 2, "https://e/2", "<p>TWO</p>", "2026-10-03T10:02:00")

    assert snapshot.searches() == [('"roman coin"', ["<p>one</p>", "<p>TWO</p>"])]
    manifest = json.loads((tmp_path / "searches/_22roman-coin_22/manifest.json").read_text())
    assert manifest["pages"] == [
        {
            "page": 1,
            "file": "page-001.html",
            "url": "https://e/1",
            "fetched_at": "2026-10-03T10:00:00",
        },
        {
            "page": 2,
            "file": "page-002.html",
            "url": "https://e/2",
            "fetched_at": "2026-10-03T10:02:00",
        },
    ]


def test_terms_lists_the_saved_searches(tmp_path):
    snapshot = Snapshot(tmp_path)
    snapshot.save_search_page("roman coin", 1, "https://e/1", "<p></p>")
    snapshot.save_search_page('"bronze age"', 1, "https://e/1", "<p></p>")

    assert sorted(snapshot.terms()) == ['"bronze age"', "roman coin"]
    assert snapshot.search_pages("no such term") == []


def test_terms_differing_only_in_case_are_rejected(tmp_path):
    snapshot = Snapshot(tmp_path)
    snapshot.save_search_page("Roman coin", 1, "https://e/1", "<p></p>")
    with pytest.raises(ValueError, match="same directory"):
        snapshot.save_search_page("roman coin", 1, "https://e/1", "<p></p>")


def test_item_pages_round_trip_and_missing_pages_are_none(tmp_path):
    snapshot = Snapshot(tmp_path)
    snapshot.save_item_page("123", "item", "https://e/itm/123", "<p>item</p>")

    assert snapshot.item_page("123", "item") == "<p>item</p>"
    assert snapshot.item_page("123", "description") is None
    assert snapshot.item_page("456", "item") is None
    manifest = json.loads((tmp_path / "items/123/manifest.json").read_text())
    assert manifest["pages"]["item"]["url"] == "https://e/itm/123"


def test_item_id_must_be_digits_so_it_cannot_escape_the_snapshot(tmp_path):
    with pytest.raises(ValueError):
        Snapshot(tmp_path).save_item_page("../etc", "item", "https://e", "")
