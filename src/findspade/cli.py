"""Command-line entry point: `findspade <command> ...`."""

import argparse
from pathlib import Path

from findspade.records import RECORDS_FILE, write_records
from findspade.snapshot import Snapshot
from findspade.terms import parse_terms_arg, read_terms_file, search_url


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="findspade")
    commands = parser.add_subparsers(required=True)

    urls = commands.add_parser("urls", help="print the first-page search URL for each term")
    _add_terms_arguments(urls)
    urls.set_defaults(func=cmd_urls)

    records = commands.add_parser("records", help="parse a snapshot into records.jsonl")
    records.add_argument(
        "snapshot", type=Path, help="snapshot directory, e.g. data/snapshots/2026-10-03"
    )
    records.set_defaults(func=cmd_records)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
