#!/usr/bin/env python
# -*- coding: utf8 -*-
import sys
import logging
from typing import Optional

logging.getLogger().addHandler(logging.StreamHandler())

from pprint import PrettyPrinter, pprint
import typer
from newsworker.extractor import FeedExtractor
from newsworker.finder import FeedsFinder
from newsworker.spec import FeedSpec, SpecAnalyzer, SpecExtractor
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.server import run_server
from newsworker.formats import (
    SCAN_FORMATS,
    SUPPORTED_FORMATS,
    format_feed,
    format_scan,
)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11"
DEFAULT_FILTERED_TEXT_URL = 150

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
def analyze(
    url: str = typer.Argument(..., help="URL to analyze and build a parsing spec for"),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to write the YAML spec to. Prints to stdout when omitted.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output. Print additional info on command execution",
    ),
):
    """Analyze a web page and generate a reusable YAML parsing spec"""
    if verbose:
        enableVerbose()
    try:
        analyzer = SpecAnalyzer(filtered_text_length=DEFAULT_FILTERED_TEXT_URL)
        spec = analyzer.analyze(url, user_agent=USER_AGENT)
        yaml_text = spec.to_yaml()
        if output:
            spec.save(output)
            logging.info(f"Spec written to {output}")
        else:
            print(yaml_text)
    except Exception as e:
        logging.error(f"Failed to analyze {url}: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@app.command()
def extract(
    url: str = typer.Argument(..., help="URL to extract feed from"),
    spec: Optional[str] = typer.Option(
        None,
        "--spec",
        "-s",
        help="Path to a YAML spec produced by 'analyze'. Falls back to dynamic "
        "extraction when omitted.",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: %s." % ", ".join(SUPPORTED_FORMATS),
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to write the result to. Prints to stdout when omitted.",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Bypass the spec and content caches for this run.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Force re-fetching the page, ignoring cached content.",
    ),
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a settings YAML file. Defaults to ~/.newsworker/config.yaml.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output. Print additional info on command execution",
    ),
):
    """Extract feed records from web page.

    Builds a parsing spec dynamically on first use and caches it (plus the
    fetched page content) so subsequent runs are faster. Pass ``--spec`` to use
    an explicit spec produced by ``analyze``.
    """
    if verbose:
        enableVerbose()
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        logging.error(
            "Unsupported format '%s'. Supported formats: %s"
            % (format, ", ".join(SUPPORTED_FORMATS))
        )
        sys.exit(2)
    try:
        settings = Settings.load(config)
        settings.user_agent = USER_AGENT
        settings.filtered_text_length = DEFAULT_FILTERED_TEXT_URL
        service = FeedService(settings=settings, use_cache=not no_cache)
        explicit_spec = FeedSpec.load(spec) if spec else None
        feed = service.get_feed(
            url, force_refresh=refresh, explicit_spec=explicit_spec
        )
        rendered = format_feed(feed, fmt=fmt, public_url=url)
        if output:
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            logging.info(f"Feed written to {output}")
        else:
            print(rendered)
    except Exception as e:
        logging.error(f"Failed to extract feed from {url}: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@app.command()
def serve(
    host: Optional[str] = typer.Option(
        None,
        "--host",
        "-h",
        help="Interface to bind. Overrides the settings value.",
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        "-p",
        help="Port to listen on. Overrides the settings value.",
    ),
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a settings YAML file. Defaults to ~/.newsworker/config.yaml.",
    ),
    cache_dir: Optional[str] = typer.Option(
        None,
        "--cache-dir",
        help="Directory for cached specs and page content. Overrides settings.",
    ),
    content_ttl: Optional[int] = typer.Option(
        None,
        "--content-ttl",
        help="Seconds a cached page stays fresh. Overrides settings.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output. Print additional info on command execution",
    ),
):
    """Run a local HTTP server exposing pages as RSS/Atom/JSON/CSV feeds.

    Generated feeds are served over GET (``/feed?url=<page>&format=atom``) so
    they can be added to any RSS reader. Parsing specs are built and cached on
    first request and page content is cached per the configured TTL.
    """
    if verbose:
        enableVerbose()
    try:
        settings = Settings.load(config)
        settings.user_agent = USER_AGENT
        if host is not None:
            settings.host = host
        if port is not None:
            settings.port = port
        if cache_dir is not None:
            settings.cache_dir = cache_dir
        if content_ttl is not None:
            settings.content_ttl = content_ttl
        run_server(settings)
    except Exception as e:
        logging.error(f"Failed to start feed server: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@app.command()
def scan(
    url: str = typer.Argument(..., help="URL to scan for feeds"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: %s." % ", ".join(SCAN_FORMATS),
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to write the result to. Prints to stdout when omitted.",
    ),
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
    fmt = format.lower()
    if fmt not in SCAN_FORMATS:
        logging.error(
            "Unsupported format '%s'. Supported formats: %s"
            % (format, ", ".join(SCAN_FORMATS))
        )
        sys.exit(2)
    try:
        r = FeedsFinder().find_feeds(url, noverify=False)
        rendered = format_scan(r, fmt=fmt, public_url=url)
        if output:
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            logging.info(f"Scan results written to {output}")
        else:
            print(rendered)
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
