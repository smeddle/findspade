"""Search terms: reading them from the user, and turning them into eBay search URLs."""

import csv
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Sold items, located in the UK, available to the US, condition used.
# Only _nkw (the keywords) and _pgn (the page number) are changed per request.
SEARCH_URL_TEMPLATE = (
    "https://www.ebay.com/sch/i.html"
    "?_nkw=&_in_kw=4&_sacat=0&LH_Sold=1&LH_ItemCondition=3000&_salic=3&LH_LocatedIn=1"
)


def parse_terms_arg(text: str) -> list[str]:
    """Split a comma-separated list of terms, e.g. '"roman coin","bronze age axe"'.

    Quotes are optional, but are needed for a term that itself contains a comma.
    """
    [row] = csv.reader([text], skipinitialspace=True)
    return [term.strip() for term in row if term.strip()]


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
    """A filesystem-safe name for a term, used as its directory name in a snapshot."""
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    if not slug:
        raise ValueError(f"Term has no usable characters for a directory name: {term!r}")
    return slug
