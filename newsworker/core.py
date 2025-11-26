#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import logging

logging.getLogger().addHandler(logging.StreamHandler())

from pprint import PrettyPrinter, pprint
import json
import datetime
import typer
from newsworker.extractor import FeedExtractor
from newsworker.finder import FeedsFinder

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11"
DEFAULT_FILTERED_TEXT_URL = 150

date_handler = lambda obj: (
    obj.isoformat() if isinstance(obj, (datetime.datetime, datetime.date)) else None
)

# logging.getLogger().addHandler(logging.StreamHandler())
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)


def enableVerbose():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )


app = typer.Typer()


@app.command()
def extract(
    url: str = typer.Argument(..., help="URL to extract feed from"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output. Print additional info on command execution",
    ),
):
    """Extract feed records from web page"""
    if verbose:
        enableVerbose()
    try:
        ext = FeedExtractor(filtered_text_length=DEFAULT_FILTERED_TEXT_URL)
        feed, session = ext.get_feed(url, user_agent=USER_AGENT)
        print(json.dumps(feed, indent=4, default=date_handler))
    except Exception as e:
        logging.error(f"Failed to extract feed from {url}: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@app.command()
def scan(
    url: str = typer.Argument(..., help="URL to scan for feeds"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output. Print additional info on command execution",
    ),
):
    """Page scanner and feed finder"""
    if verbose:
        enableVerbose()
    try:
        r = FeedsFinder().find_feeds(url, noverify=False)
        print("---")
        pprint(r)
    except Exception as e:
        logging.error(f"Failed to scan {url}: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@app.command()
def parsedate(
    datestr: str = typer.Argument(..., help="Date string to parse"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output. Print additional info on command execution",
    ),
):
    """Parses date and time strings"""
    from qddate import DateParser

    if verbose:
        enableVerbose()
    try:
        parser = DateParser(generate=True)
        res = parser.match(datestr)
        pprint(res)
    except Exception as e:
        logging.error(f"Failed to parse date '{datestr}': {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def cli():
    """Main CLI entry point"""
    app()

# if __name__ == '__main__':
#    cli()
