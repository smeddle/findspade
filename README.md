# findspade
Search online auctions for antiquities of UK provenance.

AI-coded. Do with it what thou wilt.

## Setup

Requires Python 3.11+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Dependencies are declared in `pyproject.toml`: runtime ones under `dependencies`,
development tools (`pytest`, `ruff`) under the `dev` extra.

## Usage

Search terms come either from a comma-separated list or from a file with one term per line:

```sh
findspade urls --terms '"roman coin","bronze age axe"'
findspade urls --terms-file terms.txt
```

`urls` prints the eBay sold-items search URL for each term (UK sellers, available to the US,
used condition).

## Development

```sh
pytest
ruff check . && ruff format --check .
```

Scraped data (`data/`) and raw saved pages (`samples/`) are git-ignored.
