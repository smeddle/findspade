"""Command-line entry point: `findspade <command> ...`."""

import argparse
import sys
from datetime import date
from pathlib import Path

from findspade.browser import PlaywrightBrowser, login
from findspade.fetch import HumanPace, take_snapshot
from findspade.records import RECORDS_FILE, write_records
from findspade.snapshot import Snapshot
from findspade.terms import parse_terms_arg, read_terms_file, search_url

PROFILE_DIR = Path("data/browser-profile")  # holds the eBay login cookies; git ignores data/
PROFILE_HELP = "browser profile directory holding the eBay login"


def _add_terms_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--terms",
        type=parse_terms_arg,
        help='comma-separated search terms, e.g. \'"roman coin","bronze age axe"\'',
    )
    group.add_argument(
        "--terms-file",
        type=Path,
        help="file with one search term per line ('#' starts a comment)",
    )


def _terms_from_args(args: argparse.Namespace) -> list[str]:
    return args.terms if args.terms is not None else read_terms_file(args.terms_file)


def cmd_urls(args: argparse.Namespace) -> None:
    for term in _terms_from_args(args):
        print(f"{term}\t{search_url(term)}")


def cmd_records(args: argparse.Namespace) -> None:
    count = write_records(Snapshot(args.snapshot))
    print(f"Wrote {count} records to {args.snapshot / RECORDS_FILE}")


def cmd_login(args: argparse.Namespace) -> None:
    login(args.profile)


def cmd_snapshot(args: argparse.Namespace) -> None:
    _fetch(Snapshot(args.data_dir / "snapshots" / args.date), _terms_from_args(args), args)


def cmd_resume(args: argparse.Namespace) -> None:
    snapshot = Snapshot(args.snapshot)
    terms = snapshot.terms()
    if not terms:
        sys.exit(f"No saved searches in {args.snapshot}")
    _fetch(snapshot, terms, args)


def _fetch(snapshot: Snapshot, terms: list[str], args: argparse.Namespace) -> None:
    pace = HumanPace(min_delay=args.min_delay, max_delay=args.max_delay)
    with PlaywrightBrowser(args.profile, headless=args.headless) as browser:
        take_snapshot(terms, snapshot, browser, pace)
    count = write_records(snapshot)
    print(f"Wrote {count} records to {snapshot.root / RECORDS_FILE}")


def _add_fetch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", type=Path, default=PROFILE_DIR, help=PROFILE_HELP)
    parser.add_argument(
        "--min-delay", type=float, default=4.0, help="seconds between pages, at least"
    )
    parser.add_argument(
        "--max-delay", type=float, default=12.0, help="seconds between pages, at most"
    )
    parser.add_argument("--headless", action="store_true", help="hide the browser window")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="findspade")
    commands = parser.add_subparsers(required=True)

    urls = commands.add_parser("urls", help="print the first-page search URL for each term")
    _add_terms_arguments(urls)
    urls.set_defaults(func=cmd_urls)

    login = commands.add_parser("login", help="sign in to eBay and set the delivery location")
    login.add_argument("--profile", type=Path, default=PROFILE_DIR, help=PROFILE_HELP)
    login.set_defaults(func=cmd_login)

    snapshot = commands.add_parser("snapshot", help="fetch a snapshot and write its records")
    _add_terms_arguments(snapshot)
    snapshot.add_argument(
        "--date", default=date.today().isoformat(), help="snapshot name (default: today)"
    )
    snapshot.add_argument("--data-dir", type=Path, default=Path("data"))
    _add_fetch_arguments(snapshot)
    snapshot.set_defaults(func=cmd_snapshot)

    resume = commands.add_parser(
        "resume", help="finish an interrupted snapshot, using its saved search terms"
    )
    resume.add_argument(
        "snapshot", type=Path, help="snapshot directory, e.g. data/snapshots/2026-10-03"
    )
    _add_fetch_arguments(resume)
    resume.set_defaults(func=cmd_resume)

    records = commands.add_parser("records", help="parse a snapshot into records.jsonl")
    records.add_argument(
        "snapshot", type=Path, help="snapshot directory, e.g. data/snapshots/2026-10-03"
    )
    records.set_defaults(func=cmd_records)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
