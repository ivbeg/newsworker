#!/usr/bin/env python
# -*- coding: utf8 -*-
import datetime
import json
import logging
import os
import sys
import time
from pprint import pprint
from typing import List, Optional

import typer

from newsworker import __version__
from newsworker.cache import ContentCache, SpecCache
from newsworker.extractor import FeedExtractor
from newsworker.finder import FeedsFinder
from newsworker.formats import (
    SCAN_FORMATS,
    SUPPORTED_FORMATS,
    format_feed,
    format_scan,
)
from newsworker.server import run_server
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import FeedSpec, SpecAnalyzer

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11"
DEFAULT_FILTERED_TEXT_URL = 150

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def configure_logging():
    """Install the CLI's root log handler; library imports leave logging alone."""
    logging.basicConfig(format=LOG_FORMAT, level=logging.WARNING)


def _silence_insecure_warnings():
    """``--insecure`` is an explicit choice, so do not warn on every request."""
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
            raise typer.BadParameter("Header %r must be in 'Key: Value' form" % raw)
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


def _configure_fetch_settings(
    settings,
    *,
    user_agent=None,
    insecure=False,
    ignore_robots=False,
    timeout=None,
    proxy=None,
    header=None,
    cookies=None,
    language=None,
):
    """Applies CLI fetch flags to ``settings`` (shared by ``extract`` and ``analyze``)."""
    # Compatibility helper for library callers. CLI commands use the immutable
    # layered resolver below so omitted options never overwrite file/env values.
    if user_agent is not None:
        settings.user_agent = user_agent
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
    return settings


def _resolve_fetch_settings(
    config,
    *,
    user_agent=None,
    insecure=False,
    ignore_robots=False,
    timeout=None,
    proxy=None,
    header=None,
    cookies=None,
    language=None,
    extra=None,
):
    base = Settings.resolve(config)
    cli = dict(extra or {})
    if user_agent is not None:
        cli["user_agent"] = user_agent
    if insecure:
        cli["verify_tls"] = False
        _silence_insecure_warnings()
    if ignore_robots:
        cli["respect_robots"] = False
    if timeout is not None:
        cli["request_timeout"] = timeout
    if proxy is not None:
        cli["proxy"] = proxy
    if header:
        cli["extra_headers"] = {**base.extra_headers, **_parse_headers(header)}
    if cookies is not None:
        cli["cookies_file"] = cookies
    if language is not None:
        cli["default_language"] = language
    return Settings.resolve(config, cli=cli)


def _extractor_from_settings(settings):
    """Builds a :class:`FeedExtractor` from resolved :class:`Settings`."""
    extractor = FeedExtractor(
        filtered_text_length=settings.filtered_text_length,
        max_bytes=settings.max_content_bytes,
        verify_tls=settings.verify_tls,
        respect_robots=settings.respect_robots,
        timeout=settings.request_timeout,
        proxy=settings.proxy,
        extra_headers=settings.extra_headers,
        cookies_file=settings.cookies_file,
        default_language=settings.default_language,
    )
    extractor.default_timezone = settings.default_timezone
    extractor.redirect_limit = settings.redirect_limit
    extractor.allowed_hosts = tuple(settings.allowed_hosts)
    extractor.block_private_hosts = settings.block_private_hosts
    extractor.allow_private_hosts = settings.allow_private_hosts
    extractor.trusted_proxy = settings.trusted_proxy
    return extractor


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
spec_app = typer.Typer(help="Validate and inspect parsing specifications.")
app.add_typer(spec_app, name="spec")


@spec_app.command("validate")
def spec_validate(path: str = typer.Argument(..., help="YAML parsing spec path.")):
    """Validate a parsing spec without fetching its source URL."""
    from newsworker.spec import FeedSpec

    try:
        FeedSpec.load(path).validate()
    except Exception as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"valid: {path}")


def _resolve_caches(config, specs, content):
    """Returns a ``{name: cache}`` mapping honoring the ``--specs``/``--content`` scope."""
    settings = Settings.resolve(config)
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
            "%s: %d entries, %d bytes (%s)" % (name, stats["count"], stats["bytes"], cache.dir)
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
    url: Optional[str] = typer.Argument(None, help="URL to analyze and build a parsing spec for"),
    source_file: Optional[str] = typer.Option(
        None, "--file", help="Analyze a local HTML file (use '-' for stdin)."
    ),
    base_url: Optional[str] = typer.Option(
        None, "--base-url", help="Base URL used to resolve links in local HTML."
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to write the YAML spec to. Prints to stdout when omitted.",
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
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Emit logs as structured JSON.",
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
    if json_logs:
        enableJsonLogs()
    try:
        settings = _resolve_fetch_settings(
            config,
            user_agent=user_agent,
            insecure=insecure,
            ignore_robots=ignore_robots,
            timeout=timeout,
            proxy=proxy,
            header=header,
            cookies=cookies,
            language=language,
        )
        from newsworker.sources import DocumentSource

        if bool(url) == bool(source_file):
            raise typer.BadParameter("supply exactly one URL or --file source")
        source = (
            DocumentSource.stdin(
                base_url=base_url or "",
                stream=sys.stdin.buffer,
                max_bytes=settings.max_content_bytes,
            )
            if source_file == "-"
            else DocumentSource.file(
                source_file, base_url=base_url or "", max_bytes=settings.max_content_bytes
            )
            if source_file
            else DocumentSource.url(url or "")
        )
        analyzer = SpecAnalyzer(extractor=_extractor_from_settings(settings))
        spec = analyzer.analyze(
            source.base_url,
            data=source.data,
            user_agent=settings.user_agent,
            require_items=True,
        )
        spec.input_kind = source.kind
        yaml_text = spec.to_yaml()
        if output:
            spec.save(output)
            logging.info(f"Spec written to {output}")
        else:
            print(yaml_text)
    except Exception as e:
        logging.error(f"Failed to analyze {url or source_file}: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@app.command()
def extract(
    url: Optional[str] = typer.Argument(None, help="URL to extract feed from"),
    source_file: Optional[str] = typer.Option(
        None, "--file", help="Extract from a local HTML file (use '-' for stdin)."
    ),
    base_url: Optional[str] = typer.Option(
        None, "--base-url", help="Base URL used to resolve links in local HTML."
    ),
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
    explain: bool = typer.Option(
        False, "--explain", help="Print extraction diagnostics to stderr."
    ),
    explain_json: bool = typer.Option(
        False, "--explain-json", help="Print machine-readable diagnostics to stderr."
    ),
    render: bool = typer.Option(
        False, "--render", help="Render the page with the optional browser extra."
    ),
    undated: bool = typer.Option(
        False, "--undated", help="Enable conservative undated-listing fallback."
    ),
    fail_on_empty: bool = typer.Option(
        False, "--fail-on-empty", help="Exit with status 3 when no items are extracted."
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
        settings = _resolve_fetch_settings(
            config,
            user_agent=user_agent,
            insecure=insecure,
            ignore_robots=ignore_robots,
            timeout=timeout,
            proxy=proxy,
            header=header,
            cookies=cookies,
            language=language,
            extra={
                "full_text": True if full_text else None,
                "render": True if render else None,
                "undated_fallback": True if undated else None,
            },
        )
        from newsworker.diagnostics import diagnostics_text
        from newsworker.sources import DocumentSource

        if bool(url) == bool(source_file):
            raise typer.BadParameter("supply exactly one URL or --file source")
        source = (
            DocumentSource.stdin(
                base_url=base_url or "",
                stream=sys.stdin.buffer,
                max_bytes=settings.max_content_bytes,
            )
            if source_file == "-"
            else DocumentSource.file(
                source_file, base_url=base_url or "", max_bytes=settings.max_content_bytes
            )
            if source_file
            else DocumentSource.url(url or "")
        )
        service = FeedService(settings=settings, use_cache=not no_cache)
        explicit_spec = FeedSpec.load(spec) if spec else None
        context = service.new_context(source=source.kind, base_url=source.base_url)
        feed = service.get_feed(
            source.base_url,
            force_refresh=refresh,
            explicit_spec=explicit_spec,
            max_pages=max_pages,
            data=source.data,
            context=context,
        )
        _apply_item_filters(feed, since=since, until=until, limit=limit)
        rendered = format_feed(feed, fmt=fmt, public_url=source.base_url)
        if explain_json:
            typer.echo(json.dumps(context.diagnostics.to_dict(), indent=2), err=True)
        elif explain:
            typer.echo(diagnostics_text(context.diagnostics), err=True)
        if output:
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            logging.info(f"Feed written to {output}")
        else:
            print(rendered)
        if fail_on_empty and not feed.get("items"):
            logging.error("No news items were extracted from %s", url or source_file)
            sys.exit(3)
    except SystemExit:
        raise
    except Exception as e:
        logging.error(f"Failed to extract feed from {url or source_file}: {e}")
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
        settings = Settings.resolve(
            config,
            cli={
                "host": host,
                "port": port,
                "cache_dir": cache_dir,
                "content_ttl": content_ttl,
            },
        )
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
    no_verify: bool = typer.Option(
        False,
        "--no-verify",
        help="Return candidates without fetching them for verification.",
    ),
    max_workers: int = typer.Option(
        8, "--max-workers", help="Maximum concurrent candidate verifications."
    ),
    fail_on_empty: bool = typer.Option(
        False, "--fail-on-empty", help="Exit with status 3 when no feeds are found."
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
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
            "Unsupported format '%s'. Supported formats: %s" % (format, ", ".join(SCAN_FORMATS))
        )
        sys.exit(2)
    try:
        r = FeedsFinder(Settings.resolve(config)).find_feeds(
            url,
            noverify=no_verify,
            include_sitemap=sitemap,
            max_workers=max_workers,
        )
        if r.get("error"):
            raise RuntimeError(r["error"])
        rendered = format_scan(r, fmt=fmt, public_url=url)
        if output:
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            logging.info(f"Scan results written to {output}")
        else:
            print(rendered)
        if fail_on_empty and not r.get("items"):
            logging.error("No feeds found on %s", url)
            sys.exit(3)
    except SystemExit:
        raise
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
    manifest: Optional[str] = typer.Option(
        None, "--manifest", help="Write a JSON or CSV per-source manifest."
    ),
    manifest_format: str = typer.Option(
        "json", "--manifest-format", help="Manifest format: json or csv."
    ),
    failure_policy: str = typer.Option(
        "strict", "--failure-policy", help="strict or partial-success."
    ),
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

    if max_workers <= 0:
        raise typer.BadParameter("max-workers must be positive", param_hint="--max-workers")
    if manifest_format not in {"json", "csv"}:
        raise typer.BadParameter("manifest-format must be json or csv")
    if failure_policy not in {"strict", "partial-success"}:
        raise typer.BadParameter("failure-policy must be strict or partial-success")
    settings = Settings.resolve(
        config,
        cli={"use_async": True if async_transport else None},
    )
    service = FeedService(settings=settings, use_cache=not no_cache)

    os.makedirs(output_dir, exist_ok=True)
    ext = {"markdown": "md", "jsonfeed": "json"}.get(fmt, fmt)
    urls = list(dict.fromkeys(urls))
    runtime: dict = {}
    try:
        results = service.get_feeds(urls, max_workers=max_workers, runtime=runtime)
    except TypeError as exc:  # a service without runtime reporting
        if "runtime" not in str(exc):
            raise
        results = service.get_feeds(urls, max_workers=max_workers)
    written = 0
    from newsworker.batch import BatchResult, write_manifest

    records = []
    for url in urls:
        feed = results.get(url)
        facts = runtime.get(url, {})
        transport = facts.get("transport") or ("async" if settings.use_async else "thread")
        elapsed_ms = float(facts.get("elapsed_ms") or (feed or {}).get("elapsed_ms") or 0.0)
        if not feed or "error" in feed:
            logging.warning("Skipping %s: %s", url, (feed or {}).get("error", "no result"))
            records.append(
                BatchResult(
                    source=url,
                    status="failure",
                    elapsed_ms=elapsed_ms,
                    transport=transport,
                    error_type=(feed or {}).get("error_type", "BatchError"),
                    error=(feed or {}).get("error", "no result"),
                )
            )
            continue
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        path = os.path.join(output_dir, "%s.%s" % (name, ext))
        try:
            rendered = format_feed(feed, fmt=fmt, public_url=url)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            os.replace(tmp_path, path)
        except Exception as exc:  # noqa: BLE001
            # One unwritable source must not abort the batch before the manifest.
            logging.warning("Could not write %s: %s", url, exc)
            records.append(
                BatchResult(
                    source=url,
                    status="failure",
                    elapsed_ms=elapsed_ms,
                    transport=transport,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            continue
        written += 1
        provenance = feed.get("provenance") or {}
        warnings = list(provenance.get("warnings") or [])
        records.append(
            BatchResult(
                source=url,
                status="partial" if warnings else "success",
                output_path=os.path.abspath(path),
                elapsed_ms=elapsed_ms,
                transport=transport,
                cache_state=facts.get("cache_state"),
                item_count=len(feed.get("items", [])),
                strategy=provenance.get("strategy"),
                confidence=provenance.get("confidence"),
                warnings=warnings,
            )
        )
    if manifest:
        write_manifest(records, manifest, manifest_format)
    typer.echo("Wrote %d feed file(s) to %s" % (written, output_dir))
    failures = sum(record.status == "failure" for record in records)
    if failures and (failure_policy == "strict" or written == 0):
        raise typer.Exit(code=2 if written else 3)


class WatchIterationResult(list):
    """List-compatible watch result carrying operational delivery counters."""

    def __init__(self, items=(), **status):
        super().__init__(items)
        self.status = status

    @property
    def successful(self):
        return not (
            self.status.get("failed")
            or self.status.get("pending")
            or self.status.get("terminal")
            or self.status.get("fetch_error")
        )


def _feed_meta(feed):
    return {key: feed.get(key) for key in ("title", "link", "description", "language")}


def _deliver_records(channel, dedup, records, settings, lease_seconds=60):
    """Send claimed outbox records through ``channel`` and record each outcome."""
    from newsworker.delivery import DeliveryPayload, DeliveryResult, restore_item

    delivered, failed, retried = [], 0, 0
    if not records:
        return delivered, failed, retried
    max_attempts = getattr(settings, "delivery_retries", 3)
    backoff = getattr(settings, "delivery_backoff", 1.0)
    payloads = [
        DeliveryPayload(
            restore_item(record.payload),
            record.feed_meta or {"link": record.feed},
            record.idempotency_key,
        )
        for record in records
    ]
    send_batch = getattr(channel, "send_batch", None)
    if send_batch is not None:
        results = send_batch(payloads)
    else:
        results = []
        for record, payload in zip(records, payloads, strict=True):
            # Keep our lease alive across slow sends so another worker does not
            # take over (and double-deliver) a record we are still sending.
            if record.claim_token:
                dedup.renew(record.idempotency_key, record.claim_token, lease_seconds)
            try:
                results.append(channel.send(payload))
            except Exception as exc:  # noqa: BLE001
                results.append(DeliveryResult("retryable", type(exc).__name__))
    for record, result in zip(records, results, strict=True):
        if result.successful:
            if dedup.acknowledge(record.idempotency_key, record.claim_token):
                delivered.append(record.payload)
            continue
        terminal = result.terminal or record.attempts >= max_attempts
        dedup.fail(
            record.idempotency_key,
            result.detail or result.status,
            backoff=backoff,
            terminal=terminal,
            token=record.claim_token,
        )
        failed += 1
        if not terminal:
            retried += 1
    return delivered, failed, retried


def _run_watch_iteration(
    service,
    url,
    fmt,
    dedup,
    webhook,
    max_pages,
    *,
    channels=None,
):
    """One watch tick: drain due deliveries, poll the page, deliver new items.

    Deliveries already queued are attempted before the page is fetched, so a
    source outage does not hold back items discovered earlier.
    """
    from newsworker.delivery import DeliveryPayload, StdoutChannel, WebhookChannel
    from newsworker.fetch import policy_from_settings

    runtime_settings = getattr(service, "settings", Settings())
    if channels is None:
        channels = [
            WebhookChannel(
                webhook,
                timeout=getattr(runtime_settings, "request_timeout", 30),
                policy=policy_from_settings(runtime_settings, operation="delivery"),
            )
            if webhook
            else StdoutChannel(fmt=fmt)
        ]
    channels = list(channels)
    if not channels:
        raise ValueError("at least one delivery channel is required")
    for channel in channels:
        if isinstance(channel, StdoutChannel):
            channel.fmt = fmt
        channel.validate_config()

    def destination_for(channel):
        return getattr(channel, "destination_identity", channel.name)

    def unique_items(delivered):
        result = []
        identities = set()
        for item in delivered:
            identity = str(
                item.get("unique_id") or item.get("link") or item.get("title") or id(item)
            )
            if identity not in identities:
                identities.add(identity)
                result.append(item)
        return result

    fetch_error = None
    feed = None
    if dedup is not None:
        dedup.release_expired_claims()
    delivered = []
    failed = retried = 0
    if dedup is not None:
        for channel in channels:
            prior = dedup.claim_due(
                feed=url, channel=channel.name, destination=destination_for(channel)
            )
            got, bad, again = _deliver_records(channel, dedup, prior, runtime_settings)
            delivered.extend(got)
            failed += bad
            retried += again

    try:
        try:
            feed = service.get_feed(url, max_pages=max_pages, revalidate=True)
        except TypeError as exc:
            if "revalidate" not in str(exc):
                raise
            feed = service.get_feed(url, max_pages=max_pages)
    except Exception as exc:  # noqa: BLE001
        fetch_error = f"{type(exc).__name__}: {exc}"
        logging.error("Watch fetch failed for %s: %s", url, exc)
    items = (feed or {}).get("items", [])

    if dedup is None:
        for channel in channels:
            destination = destination_for(channel)
            payloads = []
            for item in items:
                from newsworker.dedup import DedupStore

                key = DedupStore.idempotency_key(
                    url, DedupStore._uid(item), channel.name, destination
                )
                payloads.append(DeliveryPayload(item, feed, key))
            send_batch = getattr(channel, "send_batch", None)
            results = (
                send_batch(payloads)
                if send_batch is not None
                else [channel.send(payload) for payload in payloads]
            )
            for payload, result in zip(payloads, results, strict=True):
                if result.successful:
                    delivered.append(payload.item)
                else:
                    failed += 1
        return WatchIterationResult(
            unique_items(delivered),
            discovered=len(items),
            delivered=len(delivered),
            failed=failed,
            pending=failed,
            fetch_error=fetch_error,
        )

    inserted_uids = set()
    pending = terminal = 0
    for channel in channels:
        destination = destination_for(channel)
        if feed is not None:
            inserted = dedup.enqueue(
                url,
                items,
                channel=channel.name,
                destination=destination,
                feed_meta=_feed_meta(feed),
            )
            inserted_uids.update(record.uid for record in inserted)
            current = dedup.claim_due(feed=url, channel=channel.name, destination=destination)
            got, bad, again = _deliver_records(channel, dedup, current, runtime_settings)
            delivered.extend(got)
            failed += bad
            retried += again
        counts = dedup.counts(feed=url, channel=channel.name, destination=destination)
        pending += counts.get("pending", 0) + counts.get("retry", 0) + counts.get("claimed", 0)
        terminal += counts.get("terminal", 0)
    status = {
        "discovered": len(inserted_uids),
        "delivered": len(delivered),
        "retried": retried,
        "failed": failed,
        "pending": pending,
        "terminal": terminal,
        "fetch_error": fetch_error,
    }
    logging.info("watch_delivery %s", json.dumps(status, sort_keys=True))
    return WatchIterationResult(unique_items(delivered), **status)


@app.command()
def watch(
    url: str = typer.Argument(..., help="Page URL to watch."),
    interval: Optional[float] = typer.Option(
        None, "--interval", "-i", help="Seconds between polls. Overrides settings."
    ),
    webhook: Optional[str] = typer.Option(
        None, "--webhook", help="POST new items as JSON to this URL."
    ),
    channel: Optional[List[str]] = typer.Option(
        None,
        "--channel",
        help="Delivery channel; repeat for multiple destinations (stdout/webhook/smtp/telegram).",
    ),
    smtp_recipient: Optional[str] = typer.Option(
        None, "--smtp-recipient", help="Recipient used by the smtp channel."
    ),
    telegram_chat_id: Optional[str] = typer.Option(
        None, "--telegram-chat-id", help="Chat used by the telegram channel."
    ),
    format: str = typer.Option("json", "--format", "-f", help="Output format."),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", help="Pages to follow per poll. Overrides settings."
    ),
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

    if interval is not None and interval <= 0:
        raise typer.BadParameter("interval must be positive", param_hint="--interval")
    if max_pages is not None and max_pages <= 0:
        raise typer.BadParameter("max-pages must be positive", param_hint="--max-pages")
    if max_iterations < 0:
        raise typer.BadParameter(
            "max-iterations must not be negative", param_hint="--max-iterations"
        )
    settings = Settings.resolve(
        config,
        cli={"watch_interval": interval, "watch_max_pages": max_pages},
    )
    interval = settings.watch_interval
    max_pages = settings.watch_max_pages
    from newsworker.delivery import registry_from_settings

    registry = registry_from_settings(
        settings,
        webhook_url=webhook or "",
        smtp_recipient=smtp_recipient or "",
        telegram_chat_id=telegram_chat_id or "",
    )
    channel_names = list(dict.fromkeys(channel or (["webhook"] if webhook else ["stdout"])))
    try:
        selected_channels = [registry.get(name) for name in channel_names]
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--channel") from exc
    service = FeedService(settings=settings)
    dedup = DedupStore(os.path.join(settings.resolved_cache_dir(), "seen.sqlite3"))

    stop = {"flag": False}

    def _handle_signal(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    iterations = 0
    last_result = None
    try:
        while not stop["flag"]:
            try:
                last_result = _run_watch_iteration(
                    service,
                    url,
                    fmt,
                    dedup,
                    webhook,
                    max_pages,
                    channels=selected_channels,
                )
            except Exception as e:  # noqa: BLE001
                logging.error("Watch iteration failed for %s: %s", url, e)
                last_result = WatchIterationResult(fetch_error=str(e))
            # Retention runs while watching, not only on exit, so a long-lived
            # daemon's outbox does not grow without bound.
            dedup.prune(settings.delivered_retention_days)
            iterations += 1
            if max_iterations and iterations >= max_iterations:
                break
            # Sleep in short slices so a signal interrupts promptly.
            slept = 0
            while slept < interval and not stop["flag"]:
                time.sleep(min(1, interval - slept))
                slept += 1
    finally:
        dedup.prune(settings.delivered_retention_days)
        dedup.close()
    if max_iterations and last_result is not None and not last_result.successful:
        # Finite runs (cron) report problems through the exit status.
        status = last_result.status
        if status.get("fetch_error"):
            message = "Watch could not fetch %s: %s" % (url, status["fetch_error"])
        else:
            undelivered = status.get("pending", 0) + status.get("terminal", 0)
            message = "Watch completed with %d pending delivery item(s)" % undelivered
        logging.error(message)
        typer.echo(message, err=True)
        raise typer.Exit(code=1)


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
    configure_logging()
    app()
