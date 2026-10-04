"""Raw pages saved to disk, exactly as fetched, so they can be re-parsed at any time.

Layout of one snapshot (one directory per date, e.g. data/snapshots/2026-10-03):

    searches/<term slug>/manifest.json   term, and the URL and fetch time of each page
    searches/<term slug>/page-001.html
    items/<item id>/manifest.json        URL and fetch time of each page
    items/<item id>/item.html            the sold item page (which is the original listing)
    items/<item id>/description.html     the description, loaded separately by eBay
    items/<item id>/MISSING              instead of the pages, if eBay says the listing is gone
    records.jsonl                        written by records.write_records

Items are stored once per snapshot, however many search terms find them.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from findspade.terms import slugify

ITEM_PAGE_KINDS = ("item", "description")
MISSING_FILE = "MISSING"


class Snapshot:
    def __init__(self, root: Path):
        self.root = root

    def save_search_page(
        self, term: str, page: int, url: str, html: str, fetched_at: str | None = None
    ) -> None:
        directory = self.root / "searches" / slugify(term)
        directory.mkdir(parents=True, exist_ok=True)
        manifest = _read_manifest(directory) or {"term": term, "pages": []}
        if manifest["term"] != term:
            raise ValueError(
                f"Term {term!r} has the same directory as {manifest['term']!r}; "
                "eBay ignores case, so search for only one of them"
            )
        filename = f"page-{page:03d}.html"
        (directory / filename).write_text(html, encoding="utf-8")

        pages = [p for p in manifest["pages"] if p["page"] != page]
        pages.append(
            {"page": page, "file": filename, "url": url, "fetched_at": fetched_at or _now()}
        )
        manifest["pages"] = sorted(pages, key=lambda p: p["page"])
        _write_manifest(directory, manifest)

    def save_item_page(
        self, item_id: str, kind: str, url: str, html: str, fetched_at: str | None = None
    ) -> None:
        directory = self._item_directory(item_id, kind)
        directory.mkdir(parents=True, exist_ok=True)
        manifest = _read_manifest(directory) or {"item_id": item_id, "pages": {}}
        filename = f"{kind}.html"
        (directory / filename).write_text(html, encoding="utf-8")

        manifest["pages"][kind] = {"file": filename, "url": url, "fetched_at": fetched_at or _now()}
        _write_manifest(directory, manifest)

    def mark_missing(self, item_id: str, url: str) -> None:
        """Record that eBay says the item's listing is missing, so it isn't fetched again."""
        directory = self.root / "items" / _checked(item_id)
        directory.mkdir(parents=True, exist_ok=True)
        text = f"eBay said this listing is missing: {url} at {_now()}\n"
        (directory / MISSING_FILE).write_text(text, encoding="utf-8")

    def is_missing(self, item_id: str) -> bool:
        return (self.root / "items" / _checked(item_id) / MISSING_FILE).exists()

    def search_pages(self, term: str) -> list[tuple[int, str]]:
        """A term's saved results pages as (page number, HTML), in page order."""
        directory = self.root / "searches" / slugify(term)
        manifest = _read_manifest(directory)
        if manifest is None or manifest["term"] != term:
            return []
        return [
            (p["page"], (directory / p["file"]).read_text(encoding="utf-8"))
            for p in manifest["pages"]
        ]

    def terms(self) -> list[str]:
        """The search terms saved in this snapshot."""
        manifests = sorted((self.root / "searches").glob("*/manifest.json"))
        return [json.loads(path.read_text(encoding="utf-8"))["term"] for path in manifests]

    def searches(self) -> list[tuple[str, list[str]]]:
        """Each saved search as (term, HTML of each page in page order)."""
        return [(term, [html for _, html in self.search_pages(term)]) for term in self.terms()]

    def item_page(self, item_id: str, kind: str) -> str | None:
        """The saved HTML of an item's page, or None if it hasn't been fetched."""
        path = self._item_directory(item_id, kind) / f"{kind}.html"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def _item_directory(self, item_id: str, kind: str) -> Path:
        if kind not in ITEM_PAGE_KINDS:
            raise ValueError(f"Unknown item page kind {kind!r}, expected one of {ITEM_PAGE_KINDS}")
        return self.root / "items" / _checked(item_id)


def _checked(item_id: str) -> str:
    """The item id, if it is one; digits only, so it can't point outside the snapshot."""
    if not item_id.isdigit():
        raise ValueError(f"Not an eBay item id: {item_id!r}")
    return item_id


def _read_manifest(directory: Path) -> dict | None:
    path = directory / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_manifest(directory: Path, manifest: dict) -> None:
    text = json.dumps(manifest, indent=2, ensure_ascii=False)
    (directory / "manifest.json").write_text(text + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
