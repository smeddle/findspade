"""Turn a raw saved eBay page into a small, anonymised test fixture.

Usage: python tools/trim_fixture.py SRC DEST [--max-results N]

Removes scripts, styles, images, comments, the filter sidebar and most attributes, keeps
at most N real search results, shortens item links to https://www.ebay.com/itm/<id>,
replaces seller usernames with seller-1, seller-2, ... and redacts the delivery postcode.
(Scripts also contain the logged-in user's name and username.) The page structure the
parser relies on (tags, classes, ids, and a few data/aria attributes) is left intact.
"""

import argparse
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment

# The filter sidebar is not parsed and shows the logged-in user's delivery postcode.
DROP_SELECTORS = [".srp-rail__left"]
DROP_TAGS = [
    "script", "style", "svg", "noscript", "link", "meta", "iframe", "img", "header", "footer",
]  # fmt: skip
KEEP_ATTRS = {
    "class", "id", "href", "role", "type", "name", "action",
    "aria-label", "aria-disabled", "aria-current", "data-listingid",
}  # fmt: skip


def trim(html: str, max_results: int) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(DROP_TAGS) + soup.select(", ".join(DROP_SELECTORS)):
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
    return re.sub(r"_stpos=[^&\"]*", "_stpos=REDACTED", text)  # delivery postcode in links


def anonymise_sellers(text: str, soup: BeautifulSoup) -> str:
    """Replace every seller username found in search result cards, wherever it appears."""
    names = []
    for row in soup.select(".su-card-container__attributes__secondary .s-card__attribute-row"):
        first = row.find("span")
        if first and (name := first.get_text(strip=True)) not in names:
            names.append(name)
    for i, name in enumerate(names, start=1):
        text = text.replace(name, f"seller-{i}")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--max-results", type=int, default=5)
    args = parser.parse_args()

    html = trim(args.src.read_text(encoding="utf-8"), args.max_results)
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    args.dest.write_text(html, encoding="utf-8")
    print(f"{args.dest}: {len(html) // 1024} KB")


if __name__ == "__main__":
    main()
