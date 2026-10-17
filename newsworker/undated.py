"""Conservative fallback for coherent repeated article cards without dates."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from lxml import etree
from lxml.html import fromstring

from .tools import clean_url, decode_html, get_abs_url

_BLOCKED_TAGS = {"nav", "form", "select", "footer", "header", "aside"}
_BLOCKED_HINTS = {"nav", "menu", "product", "cart", "price", "login", "social", "pagination"}


def _blocked(node: Any) -> bool:
    current = node
    for _ in range(4):
        if current is None:
            break
        if str(getattr(current, "tag", "")).lower() in _BLOCKED_TAGS:
            return True
        marker = " ".join(
            [current.get("class") or "", current.get("id") or "", current.get("role") or ""]
        ).lower()
        if any(hint in marker for hint in _BLOCKED_HINTS):
            return True
        current = current.getparent()
    return False


def extract_undated_listing(
    data: bytes,
    base_url: str,
    *,
    min_items: int = 3,
    min_confidence: float = 0.75,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    document = fromstring(decode_html(data), parser=etree.HTMLParser(remove_blank_text=True))
    groups: Dict[Any, List[Any]] = defaultdict(list)
    for heading in document.xpath("//h1|//h2|//h3|//h4"):
        links = heading.xpath(".//a[@href] | ./ancestor::a[@href][1]")
        if not links or _blocked(heading):
            continue
        card = heading
        while card.getparent() is not None and card.getparent().tag not in {"body", "html"}:
            parent = card.getparent()
            siblings = [child for child in parent if isinstance(child.tag, str)]
            if len(siblings) >= min_items:
                break
            card = parent
        parent = card.getparent()
        if parent is not None:
            groups[parent].append(card)

    best_items: List[Dict[str, Any]] = []
    best_score = 0.0
    for _parent, cards in groups.items():
        unique_cards = []
        seen = set()
        for card in cards:
            identity = id(card)
            if identity not in seen:
                seen.add(identity)
                unique_cards.append(card)
        if len(unique_cards) < min_items:
            continue
        items = []
        summaries = 0
        images = 0
        semantic = 0
        for position, card in enumerate(unique_cards):
            headings = card.xpath(".//h1|.//h2|.//h3|.//h4")
            heading = headings[0] if headings else card
            title = " ".join("".join(heading.itertext()).split())
            anchors = heading.xpath(".//a[@href] | ./ancestor::a[@href][1]")
            if not anchors:
                anchors = card.xpath(".//a[@href]")
            if len(title) < 8 or not anchors:
                continue
            link = clean_url(get_abs_url(base_url, anchors[0].get("href")))
            paragraphs = card.xpath(".//p")
            description = (
                " ".join("".join(paragraphs[0].itertext()).split()) if paragraphs else title
            )
            if paragraphs:
                summaries += 1
            image_nodes = card.xpath(".//img[@src]")
            image_urls = []
            if image_nodes:
                image_urls.append(clean_url(get_abs_url(base_url, image_nodes[0].get("src"))))
                images += 1
            marker = " ".join(
                [str(card.tag), card.get("class") or "", card.get("id") or ""]
            ).lower()
            if any(hint in marker for hint in ("article", "news", "story", "post", "card")):
                semantic += 1
            unique_id = hashlib.sha256((link or title).encode("utf-8")).hexdigest()
            items.append(
                {
                    "title": title,
                    "description": description,
                    "pubdate": None,
                    "unique_id": unique_id,
                    "link": link,
                    "raw_html": etree.tostring(card, encoding="utf-8"),
                    "extra": {"links": [link], "images": image_urls},
                    "provenance": {"strategy": "undated", "position": position},
                }
            )
        if len(items) < min_items:
            continue
        if summaries < len(items) / 2 and semantic < len(items) * 0.75:
            continue
        consistency = min(1.0, len(items) / max(len(unique_cards), 1))
        score = (
            0.45
            + 0.2 * consistency
            + 0.15 * (summaries / len(items))
            + 0.1 * (images / len(items))
            + 0.1 * (semantic / len(items))
        )
        if score >= min_confidence and score > best_score:
            best_items, best_score = items, score

    title_nodes = document.xpath("//head/title")
    title = "".join(title_nodes[0].itertext()).strip() if title_nodes else f"News from {base_url}"
    feed = {
        "title": title,
        "language": "en",
        "link": base_url,
        "description": title,
        "items": best_items,
    }
    return feed, {
        "confidence": round(best_score, 3),
        "reason_codes": ["repeated_headline_cards", "undated_no_synthetic_time"]
        if best_items
        else ["no_qualified_undated_group"],
    }
