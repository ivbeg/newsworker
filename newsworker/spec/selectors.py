"""Selectors for parsing specs: generating them from elements and evaluating them.

Every selector string is interpreted as follows: an empty string is the item
element itself, ``.``, ``./…``, ``..``, ``/…`` and ``(…)`` are XPath, anything
else is CSS (via ``lxml``'s ``cssselect``).
"""

#: Heading tags preferred for item titles (h1 highest priority).
_HEADING_TAGS = ("h1", "h2", "h3", "h4")


def _element_text(node):
    """Returns visible text from an lxml element."""
    if node is None:
        return ""
    text_content = getattr(node, "text_content", None)
    if callable(text_content):
        return text_content()
    return "".join(node.itertext())


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------


def _element_classes(node):
    """Returns the list of CSS classes for an lxml element."""
    value = node.get("class")
    return value.split() if value else []


# WordPress taxonomy / per-post classes are not reliable item markers.
_TAXONOMY_CLASS_PREFIXES = ("category-", "tag-")
_STRUCTURAL_ITEM_HINTS = ("item", "grid", "entry", "card", "post-grid")


def _is_taxonomy_class(cls):
    low = cls.lower()
    return any(low.startswith(prefix) for prefix in _TAXONOMY_CLASS_PREFIXES)


def _is_post_id_class(cls):
    return bool(cls.startswith("post-") and cls[5:].isdigit())


def _item_selector_classes(classes):
    """Filters out taxonomy and per-post classes unsuitable for item selectors."""
    return [cls for cls in classes if not _is_taxonomy_class(cls) and not _is_post_id_class(cls)]


def _pick_best_item_class(classes, prefer_keywords=None):
    """Picks the best shared class for a repeating news item wrapper."""
    candidates = _item_selector_classes(classes)
    if not candidates:
        return None
    best_cls = None
    best_score = (-1, -1)
    for cls in candidates:
        low = cls.lower()
        score = 0
        if prefer_keywords:
            for keyword in prefer_keywords:
                if keyword in low:
                    score = 100
                    break
        if score < 100:
            for hint in _STRUCTURAL_ITEM_HINTS:
                if hint in low:
                    score = 10
                    break
        rank = (score, len(cls))
        if rank > best_score:
            best_score = rank
            best_cls = cls
    return best_cls


def _shared_item_selector(item_roots, prefer_keywords=None):
    """Builds a CSS selector from classes shared by every item root."""
    if not item_roots:
        return None
    tag = getattr(item_roots[0], "tag", None)
    if not isinstance(tag, str):
        return None
    if any(getattr(root, "tag", None) != tag for root in item_roots[1:]):
        return None
    common = set(_element_classes(item_roots[0]))
    for root in item_roots[1:]:
        common &= set(_element_classes(root))
    cls = _pick_best_item_class(common, prefer_keywords)
    if cls:
        return "%s.%s" % (tag, cls)
    return None


def _best_class(node, prefer_keywords=None):
    """Picks the most useful class for a node.

    When ``prefer_keywords`` is provided, a class whose name contains one of the
    keywords is preferred (this leverages the NEWS/DATE class keyword lists).
    """
    classes = _element_classes(node)
    if not classes:
        return None
    if prefer_keywords:
        for cls in classes:
            low = cls.lower()
            for keyword in prefer_keywords:
                if keyword in low:
                    return cls
    return classes[0]


def css_for_element(node, prefer_keywords=None):
    """Builds a ``tag`` or ``tag.class`` CSS selector for a single element."""
    tag = getattr(node, "tag", None)
    if not isinstance(tag, str):
        return None
    cls = _best_class(node, prefer_keywords)
    if cls:
        return "%s.%s" % (tag, cls)
    return tag


def css_for_item_element(node, prefer_keywords=None):
    """Builds an item CSS selector, skipping taxonomy and post-id classes."""
    tag = getattr(node, "tag", None)
    if not isinstance(tag, str):
        return None
    cls = _pick_best_item_class(_element_classes(node), prefer_keywords)
    if cls:
        return "%s.%s" % (tag, cls)
    return tag


def _same_tag_index(node):
    """Returns the 1-based XPath index of ``node`` among same-tag siblings."""
    parent = node.getparent()
    if parent is None:
        return 1
    tag = node.tag if isinstance(node.tag, str) else "*"
    idx = 0
    for sibling in parent.iterchildren():
        if not isinstance(sibling.tag, str):
            continue
        if sibling.tag == tag:
            idx += 1
        if sibling is node:
            return idx or 1
    return 1


def relative_xpath(root, target):
    """Builds a positional XPath from ``root`` (exclusive) to ``target``."""
    parts = []
    node = target
    while node is not None and node is not root:
        parent = node.getparent()
        if parent is None:
            break
        tag = node.tag if isinstance(node.tag, str) else "*"
        parts.append("%s[%d]" % (tag, _same_tag_index(node)))
        node = parent
    if not parts:
        return "."
    parts.reverse()
    return "./" + "/".join(parts)


def relative_selector(item_root, target, prefer_keywords=None):
    """Returns a selector from ``item_root`` to ``target``.

    Prefers a semantic ``tag.class`` CSS selector when it uniquely (first-match)
    resolves to ``target``; otherwise falls back to a positional relative XPath.
    """
    if target is item_root:
        return ""
    css = css_for_element(target, prefer_keywords)
    if css:
        try:
            matches = item_root.cssselect(css)
        except Exception:
            matches = []
        if matches and matches[0] is target:
            return css
        parent = target.getparent()
        if parent is not None and parent is not item_root:
            parent_css = css_for_element(parent, prefer_keywords)
            if parent_css:
                compound = "%s %s" % (parent_css, css)
                try:
                    matches = item_root.cssselect(compound)
                except Exception:
                    matches = []
                if matches and matches[0] is target:
                    return compound
    return relative_xpath(item_root, target)


def _is_xpath(selector):
    """Tell XPath from CSS: ``./a``, ``//a``, ``(..)`` are XPath; ``.news-card`` is CSS."""
    selector = selector.strip()
    return selector == "." or selector.startswith(("/", "(", "./", ".."))


def select_nodes(scope, selector):
    """Selects nodes under ``scope`` using the selector convention.

    Empty selector resolves to ``[scope]`` (the element itself).
    """
    if selector == "":
        return [scope]
    if _is_xpath(selector):
        try:
            return scope.xpath(selector)
        except Exception:
            return []
    try:
        return scope.cssselect(selector)
    except Exception:
        return []


_HEADING_TAGS_ALL = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def _contains(ancestor, node):
    return any(parent is ancestor for parent in node.iterancestors())


def _walk_elements(node):
    """Yields ``node`` and all descendant elements in document order."""
    yield node
    for child in node.iterchildren():
        if not isinstance(child.tag, str):
            continue
        yield from _walk_elements(child)
