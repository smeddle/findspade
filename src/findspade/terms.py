"""Search terms: reading them from the user, and turning them into eBay search URLs."""

import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Sold items, located in the UK, available to the US, condition used, 240 results per page.
# Only _nkw (the keywords) and _pgn (the page number) are changed per request.
SEARCH_URL_TEMPLATE = (
    "https://www.ebay.com/sch/i.html"
    "?_nkw=&_in_kw=4&_sacat=0&LH_Sold=1&LH_ItemCondition=3000&_salic=3&LH_LocatedIn=1"
    "&_ipg=240"
)


def parse_terms_arg(text: str) -> list[str]:
    """Split a comma-separated list of terms, e.g. '"uk antiquity",roman coin'.

    Double quotes are kept as part of the term, because eBay treats a quoted term as an
    exact phrase. A comma inside double quotes does not split the term.
    """
    terms = re.findall(r'(?:"[^"]*"|[^,])+', text)
    return [term.strip() for term in terms if term.strip()]


def read_terms_file(path: Path) -> list[str]:
    """Read one term per line, ignoring blank lines and lines starting with '#'."""
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def search_url(term: str, page: int = 1) -> str:
    """Build the search URL for a term and (1-based) results page."""
    parts = urlsplit(SEARCH_URL_TEMPLATE)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["_nkw"] = term
    if page > 1:
        params["_pgn"] = str(page)
    return urlunsplit(parts._replace(query=urlencode(params)))


def slugify(term: str) -> str:
    """A filesystem-safe, unique directory name for a term within a snapshot.

    Letters are lowercased (eBay search ignores case), spaces become '-', and any other
    character is escaped as '_' plus its hex code, so '"roman-coin"' becomes
    '_22roman_2dcoin_22' and cannot clash with 'roman coin' ('roman-coin').
    """
    out = []
    for char in term.lower():
        if char.isascii() and char.isalnum():
            out.append(char)
        elif char == " ":
            out.append("-")
        else:
            out.append(f"_{ord(char):02x}")
    return "".join(out)
