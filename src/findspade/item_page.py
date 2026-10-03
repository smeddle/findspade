"""Parse an eBay sold item page and its separately loaded description.

For sold items the page shows the original listing, so there is no further page to fetch
apart from the description, whose URL is given by description_url.

Shipping, import charges and delivery are shown for the logged-in user's delivery
location, not the actual buyer's, so scrape with eBay's delivery location set to a US ZIP.
Values are kept as the page shows them.
"""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from findspade.search_page import UnexpectedPageError, check_for_ebay_pages


@dataclass
class ItemPage:
    item_id: str
    title: str
    seller: str | None
    sale_status: str | None  # e.g. "This Buy It Now listing sold on Mon, Sep 21 at 9:41 PM."
    price: str | None  # in the seller's currency, e.g. "GBP 25.00"
    price_converted: str | None  # e.g. "US $33.14"
    best_offer_accepted: bool  # if so, the real sale price is lower than `price`
    condition: str | None  # e.g. "Pre-owned - Fair"
    location: str | None  # e.g. "Pontefract, United Kingdom"
    shipping: str | None  # e.g. "GBP 7.50 (approx US $9.94) Royal Mail International Standard"
    import_charges: str | None  # e.g. "Est. GBP 310.15 Amount confirmed at checkout"
    delivery: str | None  # e.g. "Estimated between Tue, Oct 13 and Tue, Oct 20 to 20002"
    category: list[str] = field(default_factory=list)  # breadcrumb, broadest first
    category_id: str | None = None
    item_specifics: dict[str, str] = field(default_factory=dict)
    description_url: str | None = None


def parse_item_page(html: str) -> ItemPage:
    soup = BeautifulSoup(html, "lxml")
    check_for_ebay_pages(soup)

    title = soup.select_one("h1.x-item-title__mainTitle")
    item_id = soup.select_one(".ux-layout-section--itemId .ux-textspans--BOLD")
    if title is None or item_id is None:
        raise UnexpectedPageError("Page has no item title or item number")

    specifics = _item_specifics(soup)
    description_frame = soup.select_one("iframe#desc_ifr")
    description_url = description_frame.get("src") if description_frame else None
    category_id = re.search(r"[?&]category=(\d+)", description_url or "")

    return ItemPage(
        item_id=_text(item_id),
        title=" ".join(title.get_text().split()),  # eBay splits long words across spans
        seller=_text(soup.select_one(".x-sellercard-atf__about-seller-item--seller-name")),
        sale_status=_text(soup.select_one(".d-statusmessage")),
        price=_text(soup.select_one(".x-price-primary__price")),
        price_converted=_text(soup.select_one(".x-price-approx__price")),
        best_offer_accepted=soup.find(string=re.compile("Best offer accepted")) is not None,
        condition=specifics["Condition"].split(":")[0] if "Condition" in specifics else None,
        location=_location(soup),
        shipping=_first_line(soup.select_one(".ux-labels-values--shipping")),
        import_charges=_first_line(soup.select_one(".ux-labels-values--importCharges")),
        delivery=_first_line(soup.select_one(".ux-labels-values--deliverto")),
        category=_breadcrumb(soup),
        category_id=category_id.group(1) if category_id else None,
        item_specifics=specifics,
        description_url=description_url,
    )


def parse_description(html: str) -> str:
    """The seller's description as plain text, one line per block of text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.body.get_text("\n", strip=True) if soup.body else ""


def _item_specifics(soup: BeautifulSoup) -> dict[str, str]:
    """Label/value pairs from the "Item specifics" section, e.g. {"Metal": "Bronze"}."""
    specifics = {}
    for dt in soup.select("dl.ux-layout-section-evo__item dt"):
        dd = dt.find_next_sibling("dd")
        if dd is None:
            continue
        # Long values are shown truncated, with the full text in a hidden copy.
        value = dd.select_one(".ux-expandable-textual-display-block-inline.hide") or dd
        for tag in value.select("a, button"):
            tag.decompose()
        specifics[_text(dt)] = _text(value)
    return specifics


def _location(soup: BeautifulSoup) -> str | None:
    located = soup.find(string=re.compile(r"^\s*Located in:"))
    return located.split(":", 1)[1].strip() if located else None


def _first_line(row: Tag | None) -> str | None:
    """The main text of a shipping-section row, without links and help text."""
    line = row and row.select_one(".ux-labels-values__values-content > div")
    if line is None:
        return None
    spans = line.find_all("span", class_="ux-textspans", recursive=False)
    words = [
        s.get_text(" ", strip=True) for s in spans if "ux-textspans__custom-view" not in s["class"]
    ]
    return " ".join(w for w in words if w).removesuffix(" .")


def _breadcrumb(soup: BeautifulSoup) -> list[str]:
    """Category path from the item specifics, e.g. ["Jewelry & Watches", "Brooches & Pins"]."""
    label = soup.find(string=re.compile(r"^\s*breadcrumb\s*$"))
    nav = label and label.find_parent("nav")
    return [_text(a) for a in nav.find_all("a")] if nav else []


def _text(tag: Tag | None) -> str | None:
    return tag.get_text(" ", strip=True) if tag else None
