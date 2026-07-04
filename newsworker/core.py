#!/usr/bin/env python
# -*- coding: utf8 -*-
import datetime
import json
import os
import sys
import logging
import time
from typing import List, Optional

from pprint import pprint
import typer
from newsworker import __version__
from newsworker.cache import ContentCache, SpecCache
from newsworker.finder import FeedsFinder
from newsworker.spec import FeedSpec, SpecAnalyzer
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
)


def enableVerbose():
    """Raise the root logger to DEBUG for the --verbose flag."""
    logging.getLogger().setLevel(logging.DEBUG)


class _JsonLogFormatter(logging.Formatter):
    """Emits each log record as a single-line JSON object."""

    def format(self, record):
        payload = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def enableJsonLogs():
    """Switch all root handlers to structured JSON output."""
    formatter = _JsonLogFormatter()
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)


def _parse_headers(values):
    """Parses ``["Key: Value", ...]`` CLI options into a header dict."""
    headers = {}
    for raw in values or []:
        if ":" not in raw:
            raise typer.BadParameter(
                "Header %r must be in 'Key: Value' form" % raw
            )
        key, _, value = raw.partition(":")
        headers[key.strip()] = value.strip()
    return headers


def _item_date(item):
    """Returns the ``datetime.date`` of an item's pubdate, or ``None``."""
    pubdate = item.get("pubdate")
    if pubdate is None:
        return None
    if isinstance(pubdate, datetime.datetime):
        return pubdate.date()
    if isinstance(pubdate, datetime.date):
        return pubdate
    return None


def _apply_item_filters(feed, since=None, until=None, limit=None):
    """Filters ``feed['items']`` by date range and caps the count in place."""
    items = feed.get("items", [])
    if since:
        s = datetime.date.fromisoformat(since)
        items = [i for i in items if _item_date(i) is not None and _item_date(i) >= s]
    if until:
        u = datetime.date.fromisoformat(until)
        items = [i for i in items if _item_date(i) is not None and _item_date(i) <= u]
    if limit is not None:
        items = items[:limit]
    feed["items"] = items
    return feed


def _version_callback(value: bool):
    if value:
        typer.echo(__version__)
        raise typer.Exit()


app = typer.Typer()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Print the newsworker version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """newsworker — extract feeds from pages without RSS/Atom."""


cache_app = typer.Typer(help="Inspect and manage the spec and content caches.")
app.add_typer(cache_app, name="cache")


def _resolve_caches(config, specs, content):
    """Returns a ``{name: cache}`` mapping honoring the ``--specs``/``--content`` scope."""
    settings = Settings.load(config)
    cache_dir = settings.resolved_cache_dir()
    both = not specs and not content
    caches = {}
    if specs or both:
        caches["specs"] = SpecCache(
            cache_dir,
            ttl=settings.spec_ttl,
            max_entries=settings.spec_cache_max_entries,
        )
    if content or both:
        caches["content"] = ContentCache(
            cache_dir,
            ttl=settings.content_ttl,
            max_entries=settings.content_cache_max_entries,
            max_bytes=settings.content_cache_max_bytes,
        )
    return caches


@cache_app.command("stats")
def cache_stats(
    specs: bool = typer.Option(False, "--specs", help="Only the spec cache."),
    content: bool = typer.Option(False, "--content", help="Only the content cache."),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """Report entry counts and total size per cache."""
    for name, cache in _resolve_caches(config, specs, content).items():
        stats = cache.stats()
        typer.echo(
            "%s: %d entries, %d bytes (%s)"
            % (name, stats["count"], stats["bytes"], cache.dir)
        )


@cache_app.command("list")
def cache_list(
    specs: bool = typer.Option(False, "--specs", help="Only the spec cache."),
    content: bool = typer.Option(False, "--content", help="Only the content cache."),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """List cached entries."""
    for name, cache in _resolve_caches(config, specs, content).items():
        entries = cache.list_entries()
        typer.echo("[%s] %d entries" % (name, len(entries)))
        for entry in entries:
            typer.echo("  %s (%d bytes)" % (entry["path"], entry["bytes"]))


@cache_app.command("clear")
def cache_clear(
    specs: bool = typer.Option(False, "--specs", help="Only the spec cache."),
    content: bool = typer.Option(False, "--content", help="Only the content cache."),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """Delete cached entries."""
    for name, cache in _resolve_caches(config, specs, content).items():
        removed = cache.clear()
        typer.echo("Cleared %d %s entries" % (removed, name))


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
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        help="Maximum number of items to emit.",
    ),
    max_pages: int = typer.Option(
        1,
        "--max-pages",
        help="Follow up to N 'next' links, merging items across pages.",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only items on or after this date (YYYY-MM-DD).",
    ),
    until: Optional[str] = typer.Option(
        None,
        "--until",
        help="Only items on or before this date (YYYY-MM-DD).",
    ),
    user_agent: Optional[str] = typer.Option(
        None,
        "--user-agent",
        help="Override the User-Agent used for fetching.",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        help="Override the auto-detected feed language (e.g. 'en', 'fr').",
    ),
    proxy: Optional[str] = typer.Option(
        None,
        "--proxy",
        help="Proxy URL for outgoing requests (e.g. http://host:port).",
    ),
    timeout: Optional[int] = typer.Option(
        None,
        "--timeout",
        help="HTTP request timeout in seconds.",
    ),
    header: Optional[List[str]] = typer.Option(
        None,
        "--header",
        help="Extra HTTP header 'Key: Value' (repeatable).",
    ),
    cookies: Optional[str] = typer.Option(
        None,
        "--cookies",
        help="Path to a Netscape/Mozilla cookie jar file.",
    ),
    full_text: bool = typer.Option(
        False,
        "--full-text",
        help="Follow each item link and extract the full article body (needs the "
        "'fulltext' extra: trafilatura or readability-lxml).",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Emit logs as structured JSON.",
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
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Disable TLS certificate verification for this run (not recommended).",
    ),
    ignore_robots: bool = typer.Option(
        False,
        "--ignore-robots",
        help="Fetch even when the site's robots.txt disallows it.",
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
    if json_logs:
        enableJsonLogs()
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        logging.error(
            "Unsupported format '%s'. Supported formats: %s"
            % (format, ", ".join(SUPPORTED_FORMATS))
        )
        sys.exit(2)
    try:
        settings = Settings.load(config)
        settings.user_agent = user_agent or USER_AGENT
        settings.filtered_text_length = DEFAULT_FILTERED_TEXT_URL
        if insecure:
            settings.verify_tls = False
        if ignore_robots:
            settings.respect_robots = False
        if timeout is not None:
            settings.request_timeout = timeout
        if proxy:
            settings.proxy = proxy
        if header:
            settings.extra_headers = {**settings.extra_headers, **_parse_headers(header)}
        if cookies:
            settings.cookies_file = cookies
        if language:
            settings.default_language = language
        if full_text:
            settings.full_text = True
        service = FeedService(settings=settings, use_cache=not no_cache)
        explicit_spec = FeedSpec.load(spec) if spec else None
        feed = service.get_feed(
            url,
            force_refresh=refresh,
            explicit_spec=explicit_spec,
            max_pages=max_pages,
        )
        _apply_item_filters(feed, since=since, until=until, limit=limit)
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
    sitemap: bool = typer.Option(
        False,
        "--sitemap",
        help="Also discover feed URLs from the site's sitemap.xml.",
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
        r = FeedsFinder().find_feeds(url, noverify=False, include_sitemap=sitemap)
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
def batch(
    urls_file: Optional[str] = typer.Option(
        None,
        "--urls-file",
        help="Text file with one page URL per line.",
    ),
    from_opml: Optional[str] = typer.Option(
        None,
        "--from-opml",
        help="OPML file; feeds' htmlUrl (or xmlUrl) are used as page URLs.",
    ),
    output_dir: str = typer.Option(
        ".",
        "--output-dir",
        "-d",
        help="Directory to write one feed file per URL.",
    ),
    format: str = typer.Option("json", "--format", "-f", help="Output format."),
    max_workers: int = typer.Option(4, "--max-workers", help="Concurrent fetches."),
    async_transport: bool = typer.Option(
        False,
        "--async",
        help="Use the optional aiohttp transport for concurrent page fetches.",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass caches."),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Extract feeds from many pages concurrently, one output file per URL."""
    import hashlib

    from newsworker.formats import read_opml

    if verbose:
        enableVerbose()
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        logging.error("Unsupported format '%s'." % format)
        sys.exit(2)
    if not urls_file and not from_opml:
        logging.error("Provide --urls-file or --from-opml.")
        sys.exit(2)

    urls = []
    if urls_file:
        with open(urls_file, "r", encoding="utf-8") as handle:
            urls.extend(
                line.strip() for line in handle if line.strip() and not line.startswith("#")
            )
    if from_opml:
        for entry in read_opml(from_opml):
            urls.append(entry.get("html_url") or entry["url"])

    if not urls:
        logging.error("No URLs to process.")
        sys.exit(2)

    settings = Settings.load(config)
    settings.user_agent = USER_AGENT
    settings.filtered_text_length = DEFAULT_FILTERED_TEXT_URL
    settings.use_async = async_transport
    service = FeedService(settings=settings, use_cache=not no_cache)

    os.makedirs(output_dir, exist_ok=True)
    ext = {"markdown": "md", "jsonfeed": "json"}.get(fmt, fmt)
    results = service.get_feeds(urls, max_workers=max_workers)
    written = 0
    for url in urls:
        feed = results.get(url)
        if not feed or "error" in feed:
            logging.warning("Skipping %s: %s", url, (feed or {}).get("error", "no result"))
            continue
        rendered = format_feed(feed, fmt=fmt, public_url=url)
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        path = os.path.join(output_dir, "%s.%s" % (name, ext))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        written += 1
    typer.echo("Wrote %d feed file(s) to %s" % (written, output_dir))


def _run_watch_iteration(service, url, fmt, dedup, webhook, max_pages):
    """One watch tick: extract, filter to new items, emit and/or deliver.

    Returns the list of new items (useful for tests).
    """
    from newsworker.delivery import deliver_webhook

    feed = service.get_feed(url, max_pages=max_pages)
    items = feed.get("items", [])
    new_items = dedup.filter_new(url, items) if dedup is not None else items
    if not new_items:
        return []
    emitted = dict(feed)
    emitted["items"] = new_items
    if webhook:
        deliver_webhook(webhook, new_items, feed=feed)
    else:
        print(format_feed(emitted, fmt=fmt, public_url=url))
    return new_items


@app.command()
def watch(
    url: str = typer.Argument(..., help="Page URL to watch."),
    interval: int = typer.Option(
        300, "--interval", "-i", help="Seconds between polls."
    ),
    webhook: Optional[str] = typer.Option(
        None, "--webhook", help="POST new items as JSON to this URL."
    ),
    format: str = typer.Option("json", "--format", "-f", help="Output format."),
    max_pages: int = typer.Option(1, "--max-pages", help="Pages to follow per poll."),
    max_iterations: int = typer.Option(
        0,
        "--max-iterations",
        help="Stop after N polls (0 = run until interrupted).",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Poll a page on an interval and emit/deliver only newly seen items."""
    import signal

    from newsworker.dedup import DedupStore

    if verbose:
        enableVerbose()
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        logging.error("Unsupported format '%s'." % format)
        sys.exit(2)

    settings = Settings.load(config)
    settings.user_agent = USER_AGENT
    settings.filtered_text_length = DEFAULT_FILTERED_TEXT_URL
    service = FeedService(settings=settings)
    dedup = DedupStore(os.path.join(settings.resolved_cache_dir(), "seen.sqlite3"))

    stop = {"flag": False}

    def _handle_signal(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    iterations = 0
    try:
        while not stop["flag"]:
            try:
                _run_watch_iteration(service, url, fmt, dedup, webhook, max_pages)
            except Exception as e:  # noqa: BLE001
                logging.error("Watch iteration failed for %s: %s", url, e)
            iterations += 1
            if max_iterations and iterations >= max_iterations:
                break
            # Sleep in short slices so a signal interrupts promptly.
            slept = 0
            while slept < interval and not stop["flag"]:
                time.sleep(min(1, interval - slept))
                slept += 1
    finally:
        dedup.close()


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
