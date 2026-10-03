"""Combine a snapshot's search results, item pages and descriptions into one record per item.

Where the search card and the item page both have a value, the item page's is used: it
is more detailed (e.g. the town as well as the country). The search card supplies what
the item page lacks: the sold date with its year, and the price in US dollars. Items
whose pages weren't fetched, or couldn't be parsed, get a record from the search card alone.
"""

import json
import sys
from dataclasses import asdict

from findspade.details import find_details
from findspade.item_page import ItemPage, ListingUnavailable, parse_description, parse_item_page
from findspade.search_page import SearchResult, UnexpectedPageError, parse_search_page
from findspade.snapshot import Snapshot

RECORDS_FILE = "records.jsonl"


def build_records(snapshot: Snapshot) -> list[dict]:
    results: dict[str, SearchResult] = {}  # first search result seen for each item id
    terms: dict[str, list[str]] = {}  # every search term that found each item
    for term, pages in snapshot.searches():
        for html in pages:
            for result in parse_search_page(html).results:
                results.setdefault(result.item_id, result)
                item_terms = terms.setdefault(result.item_id, [])
                if term not in item_terms:
                    item_terms.append(term)

    return [_record(snapshot, result, terms[item_id]) for item_id, result in results.items()]


def write_records(snapshot: Snapshot) -> int:
    """Write records.jsonl in the snapshot directory and return how many records it holds."""
    records = build_records(snapshot)
    with (snapshot.root / RECORDS_FILE).open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def _record(snapshot: Snapshot, result: SearchResult, search_terms: list[str]) -> dict:
    item = _item_page(snapshot, result.item_id)
    description_html = snapshot.item_page(result.item_id, "description")
    description = parse_description(description_html) if description_html else None
    title = item.title if item else result.title
    details = find_details(title, description or "", item.item_specifics if item else {})

    return {
        "item_id": result.item_id,
        "url": result.url,
        "search_terms": search_terms,
        "title": title,
        "subtitle": result.subtitle,
        "sold_date": result.sold_date.isoformat() if result.sold_date else None,
        "sale_status": item.sale_status if item else None,
        "price_usd": result.price,
        "price": item.price if item else None,
        "best_offer_accepted": item.best_offer_accepted if item else None,
        "condition": item.condition if item else None,
        "seller": item.seller if item else result.seller,
        "location": item.location if item else result.location,
        "shipping": item.shipping if item else result.shipping,
        "import_charges": item.import_charges if item else result.import_fees,
        "delivery": item.delivery if item else None,
        "category": item.category if item else [],
        "category_id": item.category_id if item else None,
        "item_specifics": item.item_specifics if item else {},
        "description": description,
        **asdict(details),
    }


def _item_page(snapshot: Snapshot, item_id: str) -> ItemPage | None:
    html = snapshot.item_page(item_id, "item")
    if html is None:
        return None
    try:
        return parse_item_page(html)
    except ListingUnavailable:
        return None  # eBay showed a catalogue product page; the search result is all there is
    except UnexpectedPageError as e:
        print(f"Warning: item {item_id}: {e}; using its search result only", file=sys.stderr)
        return None
