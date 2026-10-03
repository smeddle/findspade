"""Turn a raw saved eBay page into a small, anonymised test fixture.

Usage: python tools/trim_fixture.py SRC DEST [--max-results N] [--redact TEXT ...]

Works on search, item and description pages. Removes scripts, styles, images, comments,
the search filter sidebar, feedback and recommendation sections, and most attributes;
keeps at most N real search results; shortens item links to https://www.ebay.com/itm/<id>;
replaces seller usernames with seller-1, seller-2, ...; and redacts UK postcodes (eBay
shows the logged-in user's delivery postcode) plus any --redact text. Scripts are removed
partly because they contain the logged-in user's name and username. The structure the
parsers rely on (tags, classes, ids, and a few data/aria attributes) is left intact.
"""

import argparse
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment

DROP_TAGS = ["script", "style", "svg", "noscript", "link", "meta", "img", "header", "footer"]
DROP_SELECTORS = [
    ".srp-rail__left",  # search filter sidebar
    "iframe:not(#desc_ifr)",  # everything except the item description frame
    ".x-evo-btf-seller-card-river",  # item page: seller profile and buyers' feedback
    ".x-evo-btf-river",  # item page: recommendations below the listing
]
KEEP_ATTRS = {
    "class", "id", "href", "src", "role", "type", "name", "action",
    "aria-label", "aria-disabled", "aria-current", "data-listingid",
}  # fmt: skip
SELLER_NAME_SELECTORS = [
    ".su-card-container__attributes__secondary .s-card__attribute-row > span:first-child",
    ".x-sellercard-atf__about-seller-item--seller-name",
]
UK_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b")


def trim(html: str, max_results: int, redact: list[str]) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup.select(", ".join(DROP_SELECTORS)) + soup(DROP_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    for card in soup.select("ul.srp-results > li.s-card")[max_results:]:
        card.decompose()

    for tag in soup.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in KEEP_ATTRS}
        href = tag.get("href")
        if href and (m := re.match(r"https://(?:www\.)?ebay\.com/itm/(\d+)", href)):
            tag["href"] = f"https://www.ebay.com/itm/{m.group(1)}"

    text = anonymise_sellers(str(soup), soup)
    for secret in redact:
        text = re.sub(re.escape(secret), "REDACTED", text, flags=re.IGNORECASE)
    return UK_POSTCODE.sub("POSTCODE", text)


def anonymise_sellers(text: str, soup: BeautifulSoup) -> str:
    """Replace every seller username shown on the page, wherever it appears, in any case."""
    names = []
    for tag in soup.select(", ".join(SELLER_NAME_SELECTORS)):
        name = tag.get_text(strip=True)
        if name.lower() not in [n.lower() for n in names]:
            names.append(name)
    for i, name in enumerate(names, start=1):
        text = re.sub(re.escape(name), f"seller-{i}", text, flags=re.IGNORECASE)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--redact", action="append", default=[], help="text to replace")
    args = parser.parse_args()

    html = trim(args.src.read_text(encoding="utf-8"), args.max_results, args.redact)
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    args.dest.write_text(html, encoding="utf-8")
    print(f"{args.dest}: {len(html) // 1024} KB")


if __name__ == "__main__":
    main()
