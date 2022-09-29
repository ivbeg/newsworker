#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import logging

logging.getLogger().addHandler(logging.StreamHandler())

from pprint import PrettyPrinter, pprint
import json
import datetime
import click
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


@click.group()
def cli1():
    pass


@cli1.command()
@click.argument("url")
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Verbose output. Print additional info on command execution",
)
def extract(url, verbose):
    """Extract feed records from web page"""
    if verbose:
        enableVerbose()
    ext = FeedExtractor(filtered_text_length=DEFAULT_FILTERED_TEXT_URL)
    feed, session = ext.get_feed(sys.argv[2], user_agent=USER_AGENT)
    print(json.dumps(feed, indent=4, default=date_handler))
    pass


@click.group()
def cli2():
    pass


@cli2.command()
@click.argument("url")
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Verbose output. Print additional info on command execution",
)
def scan(url, verbose):
    """Page scanner and feed finder"""
    if verbose:
        enableVerbose()
    r = FeedsFinder().find_feeds(sys.argv[2], noverify=False)
    print("---")
    pprint(r)
    pass


@click.group()
def cli3():
    pass


@cli3.command()
@click.argument("datestr")
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Verbose output. Print additional info on command execution",
)
def parsedate(datestr, verbose):
    """Parses date and time strings"""
    from qddate import DateParser

    if verbose:
        enableVerbose()
    parser = DateParser(generate=True)
    res = parser.match(datestr)
    pprint(res)
    pass


cli = click.CommandCollection(
    sources=[cli1, cli2, cli3]
)  # , cli3, cli4, cli5, cli6, cli7, cli8, cli9, cli10, cli11, cli12])

# if __name__ == '__main__':
#    cli()
