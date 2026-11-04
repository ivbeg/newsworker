"""Deriving a :class:`FeedSpec` from a page with the dynamic date heuristics."""

import datetime
from typing import Any

from lxml import etree

from ..consts import DATE_CLASSES_KEYWORDS, NEWS_CLASSES_KEYWORDS
from ..extractor import FeedExtractor
from ..tools import pick_link_node, resolve_feed_language
from .execute import _select_item_scopes, _sibling_groups, extract_date_from_scope
from .model import HTML_TIME_PATTERN, FeedSpec, FieldRule, ItemsRule
from .selectors import (
    _HEADING_TAGS,
    _HEADING_TAGS_ALL,
    _contains,
    _element_classes,
    _element_text,
    _shared_item_selector,
    _walk_elements,
    css_for_item_element,
    css_select,
    relative_selector,
    select_nodes,
)

# Container tags that hold UI controls, not news listings.
_FORM_CONTAINER_TAGS = frozenset({"select", "form", "option", "optgroup", "datalist"})


def _signature(node):
    """Tag and classes: the wrappers of one grouped listing share both."""
    return node.tag, tuple(sorted(_element_classes(node)))


def _date_path(root, node):
    """The child tags leading from ``root`` down to ``node``."""
    tags = []
    while node is not None and node is not root:
        tags.append(node.tag)
        node = node.getparent()
    return tuple(reversed(tags))


def _follow(root, path):
    """The first element reached from ``root`` by the child tags ``path``."""
    if not path:
        return root
    for child in root:
        if child.tag == path[0]:
            found = _follow(child, path[1:])
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------
# Analysis: HTML -> FeedSpec
# ---------------------------------------------------------------------------


class SpecAnalysisError(Exception):
    """Raised when analysis cannot produce a usable parsing spec."""


class SpecAnalyzer:
    """Derives a :class:`FeedSpec` from a page using the dynamic heuristics."""

    def __init__(self, extractor=None, filtered_text_length=150):
        self.ext = extractor or FeedExtractor(filtered_text_length=filtered_text_length)

    def _parse(self, url, data=None, user_agent=None):
        if data is None:
            data = self.ext.fetch(url, user_agent)
        return self.ext.parse_page(data)

    def _item_root(self, snode, node):
        """Returns the direct child of ``snode`` that contains ``node``."""
        current = node
        while current is not None and current.getparent() is not snode:
            current = current.getparent()
        return current

    @staticmethod
    def _normalize_snode(snode):
        """Returns ``snode``, descending into ``tbody`` when it is a table."""
        if snode.tag == "table":
            for child in list(snode):
                if child.tag == "tbody":
                    return child
        return snode

    def _map_item_roots(self, snode, nodes):
        """Maps date nodes under ``snode`` to their direct-child item roots."""
        item_roots = []
        date_by_root = {}
        for node_info in nodes:
            node = node_info["node"]
            root = self._item_root(snode, node)
            if root is None:
                continue
            if root not in date_by_root:
                item_roots.append(root)
                date_by_root[root] = node
        return item_roots, date_by_root

    def _cluster_score(self, cluster_info):
        """Scores a date cluster; higher is more likely to be a news listing."""
        snode = cluster_info["snode"]
        nodes = cluster_info["nodes"]
        if snode.tag in _FORM_CONTAINER_TAGS:
            return (-1, -1, -1, -1)
        option_dates = sum(1 for info in nodes if getattr(info["node"], "tag", None) == "option")
        if option_dates and option_dates >= len(nodes) / 2:
            return (-1, -1, -1, -1)

        snode = self._normalize_snode(snode)
        if "item_roots" in cluster_info:
            item_roots, date_by_root = cluster_info["item_roots"], cluster_info["date_by_root"]
        else:
            item_roots, date_by_root = self._map_item_roots(snode, nodes)
        links = titles = 0
        for root in item_roots[:6]:
            fields = self._detect_fields(root, date_by_root.get(root))
            if fields["link"] is not None:
                links += 1
            if fields["title"][0] is not None:
                titles += 1

        news_bonus = 0
        for cls in _element_classes(snode):
            low = cls.lower()
            if any(keyword in low for keyword in NEWS_CLASSES_KEYWORDS):
                news_bonus = 1
                break
        return (links, titles, len(nodes), news_bonus)

    def _pick_best_cluster(self, clusters):
        """Returns the cluster most likely to contain repeating news items."""
        return max(clusters.items(), key=lambda kv: self._cluster_score(kv[1]))

    def candidate_clusters(self, clusters):
        """The date groups to choose from: ``clusters`` with grouped listings merged.

        A listing that puts its items into sibling wrappers (one per hour, day or
        block) yields one date group per wrapper. Wrappers with one tag and class
        whose items reach their date the same way become one group for their
        parent (:meth:`_grouped_listing`). It replaces the wrappers' groups and
        the parent's own group.
        """
        siblings: dict[tuple, list[str]] = {}
        for path, info in clusters.items():
            parent = info["snode"].getparent()
            if parent is not None:
                key = (parent, _signature(info["snode"]))
                siblings.setdefault(key, []).append(path)
        candidates = dict(clusters)
        for (parent, signature), paths in siblings.items():
            if len(paths) < 2:
                continue
            merged = self._grouped_listing(clusters, parent, signature, paths)
            if merged is None:
                continue
            for path in paths:
                candidates.pop(path, None)
            candidates[parent.getroottree().getpath(parent)] = merged
        return candidates

    def _grouped_listing(self, clusters, parent, signature, paths):
        """One date group for the sibling wrappers ``paths`` under ``parent``.

        Returns ``None`` when the wrappers' items reach their date in different
        ways, or when no CSS selector list in ``parent`` covers the items with
        nine in ten of its matches dated.
        """
        groups = [clusters[path] for path in paths]
        shapes: set[tuple] = set()
        for info in groups:
            roots, date_by_root = self._map_item_roots(
                self._normalize_snode(info["snode"]), info["nodes"]
            )
            shapes.update(_date_path(root, date_by_root[root]) for root in roots)
        if len(shapes) != 1:
            return None
        (shape,) = shapes
        # Dates clustering already read: the wrappers' and the parent's own.
        own = clusters.get(parent.getroottree().getpath(parent))
        known: dict[Any, dict] = {}
        for info in groups + ([own] if own else []):
            for node_info in info["nodes"]:
                known.setdefault(node_info["node"], node_info)

        listing = self._grouped_items(parent, signature, shape, known)
        if len(listing["item_roots"]) < 2 or listing["groups"] < 2:
            return None
        try:
            matched = css_select(parent, listing["selector"])
        except Exception:
            return None
        matched_ids = {id(node) for node in matched}
        dated = sum(1 for node in matched if _follow(node, shape) is not None)
        if dated < len(matched) * 0.9 or any(
            id(root) not in matched_ids for root in listing["item_roots"]
        ):
            return None
        return {"snode": parent, **listing}

    def _grouped_items(self, parent, signature, shape, known):
        """The items of a grouped listing, found by structure.

        Items are the children of every wrapper, and the parent's other
        children, that hold a date at ``shape``; a wrapper with one item, which
        clustering cannot pair, counts too. ``known`` maps date nodes to the
        clustering's readings; other dates are read here.
        """
        roots, date_by_root, nodes, parts, wrappers = [], {}, [], [], 0
        for child in parent.iterchildren(etree.Element):
            if _signature(child) == signature:
                holder = self._normalize_snode(child)
                prefix = css_for_item_element(child, NEWS_CLASSES_KEYWORDS)
                if holder is not child:
                    prefix += " > " + holder.tag
                prefix, members = prefix + " > ", list(holder.iterchildren(etree.Element))
            else:
                prefix, members = "", [child]
            found = 0
            for member in members:
                date_node = _follow(member, shape)
                node_info = known.get(date_node) if date_node is not None else None
                if date_node is not None and node_info is None:
                    reading = self.ext.read_date(date_node)
                    if reading is not None:
                        node_info = {"t_key": reading.key, "node": date_node, "reading": reading}
                if node_info is None:
                    continue
                roots.append(member)
                date_by_root[member] = date_node
                nodes.append(node_info)
                found += 1
                part = prefix + css_for_item_element(member, NEWS_CLASSES_KEYWORDS)
                if part not in parts:
                    parts.append(part)
            wrappers += bool(prefix and found)
        return {
            "nodes": nodes,
            "item_roots": roots,
            "date_by_root": date_by_root,
            "selector": ", ".join(parts),
            "groups": wrappers,
        }

    def _feed_title(self, document, url):
        nodes = document.xpath("//head/title")
        if nodes and nodes[0].text:
            return nodes[0].text.strip()
        return "News from " + url

    def _detect_fields(self, item_root, date_node):  # noqa: C901
        """Picks representative field nodes inside an item using tag heuristics."""
        title = None
        title_source = None
        description = None
        description_source = None
        link = None
        image = None
        for tag in _HEADING_TAGS:
            for el in _walk_elements(item_root):
                if el is date_node:
                    continue
                if el.tag == tag:
                    text = _element_text(el).strip()
                    if len(text) > 10:
                        title, title_source = el, "content"
                        break
            if title is not None:
                break
        for el in _walk_elements(item_root):
            if el is date_node:
                continue
            text = el.text.strip() if el.text else ""
            if len(text) > 10:
                if title is None:
                    title, title_source = el, "text"
                elif description is None:
                    description, description_source = el, "text"
            tail = el.tail.strip() if el.tail else ""
            if len(tail) > 10:
                if title is None:
                    title, title_source = el, "tail"
                elif description is None:
                    description, description_source = el, "tail"
            if el.tag == "img" and "src" in el.attrib and image is None:
                image = el
        title_text = _element_text(title) if title is not None else None
        link = pick_link_node(
            [el for el in _walk_elements(item_root) if el.tag == "a" and "href" in el.attrib],
            title_text,
        )
        return {
            "title": (title, title_source),
            "description": (description, description_source),
            "link": link,
            "image": image,
        }

    def _item_text_samples(self, item_roots, date_by_root, limit=12):
        """Returns title-like text snippets from discovered news items."""
        samples = []
        for root in item_roots[:limit]:
            fields = self._detect_fields(root, date_by_root[root])
            title_node, title_source = fields["title"]
            if title_node is None:
                continue
            if title_source == "tail":
                text = (title_node.tail or "").strip()
            elif title_source == "content":
                text = _element_text(title_node).strip()
            else:
                text = (title_node.text or "").strip()
            if not text:
                text = _element_text(title_node).strip()
            if len(text) >= 10:
                samples.append(text)
        return samples

    def _resolve_language(self, document, text_samples=None):
        return resolve_feed_language(
            override=getattr(self.ext, "default_language", None),
            document=document,
            content_language=getattr(self.ext, "_last_content_language", None),
            text_samples=text_samples,
        )

    def analyze(self, url, data=None, user_agent=None, require_items=False, context=None):
        if context is None:
            return self._analyze_active(
                url, data=data, user_agent=user_agent, require_items=require_items
            )
        with self.ext.activate_context(context):
            return self._analyze_active(
                url, data=data, user_agent=user_agent, require_items=require_items
            )

    def _analyze_active(self, url, data=None, user_agent=None, require_items=False):  # noqa: C901
        """Analyzes ``url`` (or provided ``data``) and returns a ``FeedSpec``.

        When ``require_items`` is true, raises :class:`SpecAnalysisError` if the
        page does not contain a detectable news listing.
        """
        document = self._parse(url, data=data, user_agent=user_agent)
        spec = FeedSpec(
            source_url=url,
            analyzed_at=datetime.datetime.now().isoformat(timespec="seconds"),
            language=self._resolve_language(document),
        )
        if document is None:
            if require_items:
                raise SpecAnalysisError("Failed to fetch or parse page content")
            return spec
        spec.title = self._feed_title(document, url)

        self.ext.init_session()
        try:
            clusters = self.ext.getclusters(document, url)
        finally:
            self.ext.clear_session()

        if not clusters:
            if require_items:
                raise SpecAnalysisError("No dated news listings detected on this page")
            return spec

        best_path, best = self._pick_best_cluster(self.candidate_clusters(clusters))
        snode = self._normalize_snode(best["snode"])
        grouped = best.get("selector")
        patterns = list(dict.fromkeys(n["t_key"] for n in best["nodes"] if n.get("t_key")))
        if grouped:
            item_roots, date_by_root = best["item_roots"], best["date_by_root"]
        else:
            # Map every date node to its item root (direct child of snode).
            item_roots, date_by_root = self._map_item_roots(snode, best["nodes"])

        if not item_roots:
            if require_items:
                raise SpecAnalysisError(
                    "Found date patterns but could not group them into individual news items"
                )
            return spec

        spec.language = self._resolve_language(
            document,
            text_samples=self._item_text_samples(item_roots, date_by_root),
        )

        flat = None if grouped else self._flat_layout(snode, item_roots)
        if flat is not None:
            # Heading, date line and teaser are siblings with no wrapper per
            # item: the heading before each date starts the item.
            spec.items, spec.fields = (
                flat[0],
                self._build_scope_field_rules(flat[1], date_by_root, patterns),
            )
        elif grouped:
            # Items in sibling wrappers and between them: the selector list
            # checked by ``_grouped_listing``; links checked on every item.
            spec.items = ItemsRule(selector=grouped, selector_type="css", container=best_path)
            spec.fields = self._build_field_rules(item_roots, date_by_root, patterns)
            self._agree_link_rule(spec.fields, item_roots)
        else:
            # Item selector: prefer a semantic tag.class shared by item roots.
            spec.items = self._build_items_rule(document, snode, item_roots)

            # Field rules: use the first item root that has a usable date + text.
            spec.fields = self._build_field_rules(item_roots, date_by_root, patterns)

        # Validate against the same document; fall back to positional if empty.
        if flat is None and not grouped and not self._validate(document, spec):
            spec.items = self._positional_items_rule(document, snode, item_roots)
            if not self._validate(document, spec):
                # Keep the semantic attempt; extraction may still work partially.
                pass
        if require_items:
            if not spec.fields:
                raise SpecAnalysisError(
                    "Could not derive extraction rules for news items on this page"
                )
            if "title" not in spec.fields and "link" not in spec.fields:
                raise SpecAnalysisError(
                    "Could not derive title or link extraction rules for news items on this page"
                )
            if not self._validate(document, spec):
                raise SpecAnalysisError(
                    "Built selectors matched fewer than 2 news items on this page"
                )
            if not self._validate_dates(document, spec):
                raise SpecAnalysisError(
                    "Built selectors could not parse dates from news items on this page"
                )
        return spec

    @staticmethod
    def _previous_element(node):
        previous = node.getprevious()
        while previous is not None and not isinstance(previous.tag, str):
            previous = previous.getprevious()
        return previous

    def _flat_layout(self, snode, item_roots):
        """Detect items made of sibling elements led by a heading.

        Returns ``(items_rule, sample_scope)`` or ``None``. Applies when at least
        90% of the date-bearing children of the container are directly preceded
        by an undated heading; each item then runs from its heading to the next.
        """
        # A headline may itself contain a date ("2026-10-07: ..."); such a
        # heading is the lead of the item that follows, not an item of its own.
        roots = [root for root in item_roots if str(root.tag).lower() not in _HEADING_TAGS_ALL]
        if len(roots) < 2:
            return None
        leads = []
        for root in roots:
            previous = self._previous_element(root)
            if previous is not None and str(previous.tag).lower() in _HEADING_TAGS_ALL:
                leads.append(previous)
        if len(leads) < max(2, int(len(roots) * 0.9 + 0.999)):
            return None
        selector = css_for_item_element(leads[0]) or str(leads[0].tag).lower()
        try:
            matched = css_select(snode, selector)
        except Exception:
            return None
        matched = [node for node in matched if node.getparent() is snode]
        if any(lead not in matched for lead in leads) or len(matched) > len(leads) + 1:
            return None
        rule = ItemsRule(
            selector=selector,
            selector_type="css",
            container=snode.getroottree().getpath(snode),
            group="siblings",
        )
        return rule, _sibling_groups([leads[0], leads[1]])[0]

    def _build_scope_field_rules(self, scope, date_by_root, patterns):
        """Field rules for an item spread over sibling elements (``scope``).

        Each selector is relative to the scope member holding the target; the
        extractor tries scope members in order, so the leading heading wins
        for the title and link.
        """
        heading = scope[0]
        date_root = next((node for node in scope if node in date_by_root), None)
        if date_root is None:
            return {}
        date_node = date_by_root[date_root]
        fields = {}
        date_source = "text" if (date_node.text and date_node.text.strip()) else "tail"
        if patterns and HTML_TIME_PATTERN in patterns and date_node.get("datetime"):
            date_source = "attr:datetime"
        fields["date"] = FieldRule(
            selector=relative_selector(date_root, date_node, DATE_CLASSES_KEYWORDS),
            source=date_source,
            patterns=patterns or None,
            required=True,
        )
        fields["title"] = FieldRule(selector="", source="content")
        title_text = _element_text(heading)
        link = pick_link_node(
            [el for member in scope for el in _walk_elements(member) if el.tag == "a"],
            title_text,
        )
        if link is not None:
            holder = next(member for member in scope if link is member or _contains(member, link))
            fields["link"] = FieldRule(
                selector=relative_selector(holder, link),
                source="attr:href",
                absolute=True,
            )
        tail = (date_root.tail or "").strip()
        if len(tail) > 10:
            fields["description"] = FieldRule(selector="", source="tail")
        return fields

    def _min_items_matched(self, item_count):
        """Minimum nodes a CSS item selector must match inside the container."""
        if item_count <= 2:
            return item_count
        return max(2, int(item_count * 0.9 + 0.999))

    def _css_items_rule(self, document, snode, item_roots, selector):
        container = document.getroottree().getpath(snode)
        try:
            matched = css_select(snode, selector)
        except Exception:
            matched = []
        min_needed = self._min_items_matched(len(item_roots))
        if len(matched) >= min_needed and self._selector_specific_enough(
            selector, len(matched), len(item_roots)
        ):
            return ItemsRule(
                selector=selector,
                selector_type="css",
                container=container,
                stride=1,
            )
        return None

    def _build_items_rule(self, document, snode, item_roots):
        shared = _shared_item_selector(item_roots, NEWS_CLASSES_KEYWORDS)
        if shared:
            rule = self._css_items_rule(document, snode, item_roots, shared)
            if rule is not None:
                return rule

        counts: dict[str, int] = {}
        for root in item_roots:
            css = css_for_item_element(root, NEWS_CLASSES_KEYWORDS)
            if css:
                counts[css] = counts.get(css, 0) + 1
        if counts:
            selector = max(counts.items(), key=lambda kv: kv[1])[0]
            rule = self._css_items_rule(document, snode, item_roots, selector)
            if rule is not None:
                return rule
        return self._positional_items_rule(document, snode, item_roots)

    @staticmethod
    def _selector_specific_enough(selector, matched_count, item_count):
        """Returns whether a CSS item selector is precise enough to use.

        Bare tag selectors (``div``, ``tr``, …) and selectors that match far
        more nodes than discovered news items are rejected in favour of a
        positional fallback.
        """
        if item_count <= 0:
            return False
        if "." not in selector:
            return matched_count <= item_count * 1.1
        if matched_count <= item_count * 1.1:
            return True
        # Date clustering can miss an item; allow a small overshoot for
        # specific class selectors.
        return matched_count <= item_count + 1

    def _positional_items_rule(self, document, snode, item_roots):
        container = document.getroottree().getpath(snode)
        stride = self._infer_stride(snode, item_roots)
        return ItemsRule(
            selector="./*",
            selector_type="xpath",
            container=container,
            stride=stride,
        )

    def _infer_stride(self, snode, item_roots):
        indices = []
        for root in item_roots:
            try:
                indices.append(snode.index(root))
            except (ValueError, TypeError):
                continue
        indices.sort()
        gaps: dict[int, int] = {}
        for i in range(1, len(indices)):
            diff = indices[i] - indices[i - 1]
            if diff > 0:
                gaps[diff] = gaps.get(diff, 0) + 1
        if not gaps:
            return 1
        return max(gaps.items(), key=lambda kv: kv[1])[0]

    def _build_field_rules(self, item_roots, date_by_root, patterns):
        fields = {}
        sample_root = None
        for root in item_roots:
            if date_by_root.get(root) is not None:
                sample_root = root
                break
        if sample_root is None:
            sample_root = item_roots[0]
        date_node = date_by_root.get(sample_root)

        # Date rule.
        if date_node is not None:
            date_source = "text"
            if not (date_node.text and date_node.text.strip()):
                date_source = "tail"
            if (
                patterns
                and HTML_TIME_PATTERN in patterns
                and (
                    isinstance(getattr(date_node, "tag", None), str)
                    and date_node.tag == "time"
                    and date_node.get("datetime")
                )
            ):
                date_source = "attr:datetime"
            fields["date"] = FieldRule(
                selector=relative_selector(sample_root, date_node, DATE_CLASSES_KEYWORDS),
                source=date_source,
                patterns=patterns or None,
                required=True,
            )

        detected = self._detect_fields(sample_root, date_node)

        title_node, title_source = detected["title"]
        if title_node is not None:
            fields["title"] = FieldRule(
                selector=relative_selector(sample_root, title_node),
                source=title_source,
            )

        desc_node, desc_source = detected["description"]
        if desc_node is not None:
            fields["description"] = FieldRule(
                selector=relative_selector(sample_root, desc_node),
                source=desc_source,
            )

        link_node = detected["link"]
        if link_node is not None:
            fields["link"] = FieldRule(
                selector=relative_selector(sample_root, link_node),
                source="attr:href",
                absolute=True,
            )

        image_node = detected["image"]
        if image_node is not None:
            fields["image"] = FieldRule(
                selector=relative_selector(sample_root, image_node),
                source="attr:src",
                absolute=True,
            )
        return fields

    def _agree_link_rule(self, fields, item_roots):
        """Use the link rule that finds the article link in the most items.

        The items of a grouped listing differ: some start with a category link,
        others hold only the headline link. The sample item's link selector is
        compared with the link holding the title heading (``.//a[.//h3]``) and
        the link inside it (``h3 a``) on every item.
        """
        rule, title = fields.get("link"), fields.get("title")
        if rule is None or title is None:
            return
        titles = [next(iter(select_nodes(root, title.selector)), None) for root in item_roots]
        tags = {str(node.tag) for node in titles if node is not None}
        candidates = [rule.selector]
        if len(tags) == 1 and next(iter(tags)) in _HEADING_TAGS_ALL:
            tag = next(iter(tags))
            candidates += [".//a[.//%s]" % tag, "%s a" % tag]
        wanted = [
            pick_link_node(
                [el for el in _walk_elements(root) if el.tag == "a" and el.get("href")],
                _element_text(node) if node is not None else None,
            )
            for root, node in zip(item_roots, titles, strict=True)
        ]

        def agreement(selector):
            found = 0
            for root, want in zip(item_roots, wanted, strict=True):
                links = [el for el in select_nodes(root, selector) if el.get("href")]
                found += bool(links) and links[0] is want
            return found

        rule.selector = max(candidates, key=agreement)

    def _validate(self, document, spec):
        try:
            scopes = _select_item_scopes(document, spec.items)
        except Exception:
            return False
        return len(scopes) >= 2

    def _validate_dates(self, document, spec):
        """Returns whether at least one item scope yields a parseable date."""
        date_rule = spec.fields.get("date")
        if date_rule is None:
            return True
        try:
            scopes = _select_item_scopes(document, spec.items)
        except Exception:
            return False
        for scope in scopes[:3]:
            _, pubdate = extract_date_from_scope(self.ext, scope, date_rule, date_rule.patterns)
            if pubdate is not None:
                return True
        return False
