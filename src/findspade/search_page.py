"""Parse an eBay sold-items search results page into SearchResult records.

Values are kept as the page shows them (e.g. price "$106.04"), except the sold date.
Turning prices and delivery text into numbers is left to the analysis stage.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag


class UnexpectedPageError(Exception):
    """The page is not a search results page, e.g. a verification page."""


class NotLoggedInError(UnexpectedPageError):
    """eBay showed its sign-in page instead of the results."""


class EbayErrorPage(UnexpectedPageError):
    """eBay's own "Something went wrong on our end" page; reloading usually works."""


class BrowserCheckPage(UnexpectedPageError):
    """eBay's "Checking your browser" bot check, which normally redirects to the content."""


# What a loaded search page shows: results, or a "no exact matches" message.
SEARCH_PAGE_READY = "ul.srp-results, .srp-save-null-search"


def check_for_ebay_pages(soup: BeautifulSoup) -> None:
    """Raise if eBay showed its sign-in page or its error page instead of the content."""
    if soup.find("form", id="signin-form"):
        raise NotLoggedInError("Got the eBay sign-in page; is the browser logged in?")
    if soup.find(string=re.compile("Something went wrong on our end")):
        raise EbayErrorPage("Got eBay's 'Something went wrong on our end' page")
    if soup.find(string=re.compile("Checking your browser before you access eBay")):
        raise BrowserCheckPage("eBay's 'Checking your browser' page didn't clear by itself")


@dataclass
class SearchResult:
    item_id: str
    url: str
    title: str
    subtitle: str | None  # often the condition, e.g. "Pre-Owned", but sellers can set it
    sold_date: date | None
    price: str  # e.g. "$106.04"
    shipping: str | None  # e.g. "+$24.63 shipping estimate", "Shipping not specified"
    import_fees: str | None  # e.g. "Import fees paid at checkout"
    location: str | None  # e.g. "United Kingdom"
    seller: str | None


@dataclass
class SearchPage:
    total_results: int | None  # eBay's own (approximate) count, when shown
    has_next_page: bool
    results: list[SearchResult]
    ship_to: str | None = None  # the logged-in user's delivery location, e.g. "20002"


def parse_search_page(html: str) -> SearchPage:
    soup = BeautifulSoup(html, "lxml")
    check_for_ebay_pages(soup)

    results_list = soup.select_one("ul.srp-results")
    if results_list is None and not soup.select_one(".srp-save-null-search"):
        raise UnexpectedPageError("Page has neither search results nor a 'no matches' message")

    # Only cards inside the results list are real results; eBay also puts
    # "Shop on eBay" placeholder cards elsewhere on the page.
    cards = results_list.select(":scope > li.s-card") if results_list else []

    return SearchPage(
        total_results=_total_results(soup),
        has_next_page=soup.select_one("a.pagination__next[href]") is not None,
        results=[_parse_card(card) for card in cards],
        ship_to=_text(soup.select_one(".shipping-entry .zipcode-text")),
    )


def _total_results(soup: BeautifulSoup) -> int | None:
    heading = soup.select_one(".srp-controls__count-heading")
    match = heading and re.match(r"([\d,]+) results?", heading.get_text(" ", strip=True))
    return int(match.group(1).replace(",", "")) if match else None


def _parse_card(card: Tag) -> SearchResult:
    item_id = card["data-listingid"]

    shipping = import_fees = location = None
    for row in card.select(".su-card-container__attributes__primary .s-card__attribute-row"):
        text = row.get_text(" ", strip=True)
        if text.startswith("Located in "):
            location = text.removeprefix("Located in ")
        elif text.startswith("Import fees"):
            import_fees = text
        elif re.search(r"delivery|shipping", text, re.IGNORECASE):
            shipping = text

    seller_row = card.select_one(".su-card-container__attributes__secondary .s-card__attribute-row")
    seller_name = seller_row and seller_row.find("span")

    return SearchResult(
        item_id=item_id,
        url=f"https://www.ebay.com/itm/{item_id}",
        title=_text(card.select_one(".s-card__title .su-styled-text")),
        subtitle=_text(card.select_one(".s-card__subtitle")),
        sold_date=_sold_date(_text(card.select_one(".s-card__caption"))),
        price=_text(card.select_one(".s-card__price")),
        shipping=shipping,
        import_fees=import_fees,
        location=location,
        seller=_text(seller_name),
    )


def _sold_date(caption: str | None) -> date | None:
    """'Sold  Sep 27, 2026' -> date(2026, 9, 27)"""
    match = caption and re.match(r"Sold\s+(\w{3} \d{1,2}, \d{4})", caption)
    return datetime.strptime(match.group(1), "%b %d, %Y").date() if match else None


def _text(tag: Tag | None) -> str | None:
    return tag.get_text(" ", strip=True) if tag else None
