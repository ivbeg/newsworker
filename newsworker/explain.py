"""Explain an extraction: which date clusters a page has, which one won, why.

``newsworker explain URL`` runs the normal pipeline and reports, alongside the
items, the evidence behind them: every repeated group of dates on the page
with its score, the spec a fresh analysis would write, every strategy that was
tried, and plain-language hints when the result looks wrong (no dates, items
linking to the listing itself, a cached spec that stopped matching).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from html import escape
from typing import Any, Dict, List, Optional

from lxml import etree
from lxml.html import fromstring

from .formats import _date_handler
from .tools import decode_html


@dataclass
class ClusterReport:
    container: str
    dates: int
    links: int
    titles: int
    news_class: bool
    patterns: List[str]
    samples: List[str]
    chosen: bool = False


@dataclass
class Explanation:
    url: str
    strategy: Optional[str]
    confidence: float
    clusters: List[ClusterReport]
    spec_yaml: Optional[str]
    attempts: List[Dict[str, Any]]
    warnings: List[str]
    hints: List[str]
    items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _node_text(node) -> str:
    text = (node.text or "").strip() or (node.tail or "").strip()
    return " ".join(text.split())[:80]


def _clusters(service, url: str, data: bytes, context) -> List[ClusterReport]:
    from .spec import SpecAnalyzer

    try:
        document = fromstring(decode_html(data), parser=etree.HTMLParser(remove_blank_text=True))
    except (ValueError, etree.ParserError, etree.XMLSyntaxError):
        return []
    analyzer = SpecAnalyzer(extractor=service.extractor)
    extractor = service.extractor
    with extractor.activate_context(context):
        extractor.init_session()
        try:
            clusters = extractor.getclusters(document, url)
        finally:
            extractor.clear_session()
        if not clusters:
            return []
        chosen_path, _best = analyzer._pick_best_cluster(clusters)
        reports = []
        for path, info in clusters.items():
            links, titles, dates, news_bonus = analyzer._cluster_score(info)
            nodes = info["nodes"]
            reports.append(
                ClusterReport(
                    container=path,
                    dates=len(nodes),
                    links=max(0, links),
                    titles=max(0, titles),
                    news_class=bool(news_bonus > 0),
                    patterns=sorted({str(n.get("t_key")) for n in nodes if n.get("t_key")}),
                    samples=[_node_text(n["node"]) for n in nodes[:3]],
                    chosen=path == chosen_path,
                )
            )
    reports.sort(key=lambda r: (not r.chosen, -r.links, -r.titles, -r.dates))
    return reports


def _fresh_spec(service, url: str, data: bytes, context) -> Optional[str]:
    from .spec import SpecAnalyzer

    try:
        with service.extractor.activate_context(context):
            spec = SpecAnalyzer(extractor=service.extractor).analyze(url, data=data)
    except Exception:  # noqa: BLE001 - the report should still render
        return None
    return spec.to_yaml() if spec.fields else None


def _hints(url, clusters, feed, diagnostics) -> List[str]:
    items = feed.get("items", []) or []
    hints = []
    strategy = diagnostics.chosen_strategy if diagnostics else None
    if not clusters and not items:
        hints.append(
            "No repeated dates were found on the page. If the listing is built by "
            "JavaScript, try --render; if it shows no dates at all, try --undated."
        )
    elif clusters and not items:
        hints.append(
            "Dates were found but no items could be built around them. Check the chosen "
            "group below; an explicit spec (newsworker analyze) can be corrected by hand."
        )
    best = next((c for c in clusters if c.chosen), None)
    if best is not None and best.links == 0:
        hints.append(
            "The chosen date group has no links near its dates, so it may be a calendar, "
            "an archive menu or page metadata rather than the news list."
        )
    if items:
        page_links = sum(1 for item in items if item.get("link") in (url, None))
        if page_links > len(items) / 2:
            hints.append(
                f"{page_links} of {len(items)} items link to the listing page itself: the "
                "headline links were not detected."
            )
        undated = sum(1 for item in items if item.get("pubdate") is None)
        if undated and strategy != "undated":
            hints.append(f"{undated} of {len(items)} items have no publication date.")
    if strategy == "rebuilt_spec":
        hints.append(
            "The cached spec matched nothing and was re-analysed: the site layout probably changed."
        )
    if strategy == "structured":
        hints.append("Items come from the page's JSON-LD / microdata, not from visible dates.")
    if strategy == "undated":
        hints.append("No dates were usable; items come from the undated-listing fallback.")
    return hints


def explain(service, url: str, data: Optional[bytes] = None, *, source: str = "network"):
    """Run the pipeline for ``url`` (or local ``data``) and collect the evidence."""
    context = service.new_context(source=source, base_url=url)
    if data is None:
        data = service._fetch(url, context=context)
        url = context.response_meta.get("effective_url") or url
    feed, diagnostics = service.get_feed_with_diagnostics(
        url, data=data, context=service.new_context(source=source, base_url=url)
    )
    clusters = _clusters(service, url, data, service.new_context(base_url=url))
    spec_yaml = _fresh_spec(service, url, data, service.new_context(base_url=url))
    return Explanation(
        url=url,
        strategy=diagnostics.chosen_strategy if diagnostics else None,
        confidence=diagnostics.confidence if diagnostics else 0.0,
        clusters=clusters,
        spec_yaml=spec_yaml,
        attempts=[dataclasses.asdict(a) for a in diagnostics.attempts] if diagnostics else [],
        warnings=list(diagnostics.warnings) if diagnostics else [],
        hints=_hints(url, clusters, feed, diagnostics),
        items=[
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "pubdate": item.get("pubdate"),
            }
            for item in feed.get("items", [])[:25]
        ],
    )


def to_text(report: Explanation) -> str:
    lines = [
        f"url: {report.url}",
        f"strategy: {report.strategy or 'none'}  confidence: {report.confidence:.2f}",
        f"items: {len(report.items)}",
    ]
    for hint in report.hints:
        lines.append(f"hint: {hint}")
    for warning in report.warnings:
        lines.append(f"warning: {warning}")
    lines.append(f"date groups: {len(report.clusters)}")
    for cluster in report.clusters[:10]:
        mark = "*" if cluster.chosen else " "
        lines.append(
            f" {mark} {cluster.dates} dates, {cluster.links} linked, {cluster.titles} titled "
            f"{cluster.container} e.g. {', '.join(cluster.samples)}"
        )
    for attempt in report.attempts:
        lines.append(
            f"attempt {attempt['strategy']}: {attempt['status']}, {attempt['item_count']} items"
        )
    for item in report.items[:10]:
        lines.append(
            f"  {_date_handler(item['pubdate']) if item['pubdate'] else '-'}  "
            f"{item['title']}  <{item['link']}>"
        )
    return "\n".join(lines)


def to_json(report: Explanation) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=_date_handler)


_STYLE = (
    "body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;"
    "color:#1d1d1f}h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:2rem}"
    "table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{border-bottom:1px solid #ddd;"
    "padding:.35rem .5rem;text-align:left;vertical-align:top}tr.chosen{background:#eef6ff}"
    ".hint{background:#fff7e0;border-left:4px solid #e0a800;padding:.5rem .75rem;margin:.5rem 0}"
    "code,pre{font:13px ui-monospace,monospace}pre{background:#f5f5f7;padding:1rem;overflow:auto}"
    ".muted{color:#666}"
)


def to_html(report: Explanation) -> str:
    """A standalone page; every value from the page is escaped, scripts are blocked."""

    def cell(value) -> str:
        return f"<td>{escape(str(value))}</td>"

    rows = []
    for cluster in report.clusters:
        rows.append(
            f'<tr class="{"chosen" if cluster.chosen else ""}">'
            + cell("chosen" if cluster.chosen else "")
            + cell(cluster.dates)
            + cell(cluster.links)
            + cell(cluster.titles)
            + f"<td><code>{escape(cluster.container)}</code></td>"
            + cell("; ".join(cluster.samples))
            + "</tr>"
        )
    items = "".join(
        "<tr>"
        + cell(_date_handler(item["pubdate"]) if item["pubdate"] else "—")
        + cell(item["title"] or "")
        + f"<td><code>{escape(str(item['link'] or ''))}</code></td></tr>"
        for item in report.items
    )
    attempts = "".join(
        "<tr>" + cell(a["strategy"]) + cell(a["status"]) + cell(a["item_count"]) + "</tr>"
        for a in report.attempts
    )
    hints = "".join(f'<p class="hint">{escape(h)}</p>' for h in report.hints + report.warnings)
    spec = (
        f"<pre>{escape(report.spec_yaml)}</pre>"
        if report.spec_yaml
        else '<p class="muted">A fresh analysis could not derive a spec for this page.</p>'
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>newsworker explain — {escape(report.url)}</title><style>{_STYLE}</style></head>
<body>
<h1>Why newsworker extracted what it did</h1>
<p><code>{escape(report.url)}</code><br>
Strategy <b>{escape(report.strategy or "none")}</b>, {len(report.items)} items,
heuristic confidence {report.confidence:.2f}.</p>
{hints}
<h2>Repeated date groups ({len(report.clusters)})</h2>
<p class="muted">The highlighted group was chosen: groups with more linked and titled items win.</p>
<table><tr><th></th><th>Dates</th><th>Linked</th><th>Titled</th><th>Container</th>
<th>Examples</th></tr>{"".join(rows)}</table>
<h2>Strategies tried</h2>
<table><tr><th>Strategy</th><th>Result</th><th>Items</th></tr>{attempts}</table>
<h2>Items</h2>
<table><tr><th>Date</th><th>Title</th><th>Link</th></tr>{items}</table>
<h2>Spec a fresh analysis would write</h2>
<p class="muted">Save it with <code>newsworker analyze</code>, edit the selectors, and use it with
<code>extract --spec</code>.</p>
{spec}
</body></html>
"""
