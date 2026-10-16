"""
Parsing specification (spec) support for newsworker.

A spec captures, in a serializable (YAML) form, how to extract a news feed from
a given site layout: how to locate the repeating news items and how to pull the
individual fields (date, title, link, description, image) out of each item.

Two entry points are provided:

* :class:`SpecAnalyzer` runs the existing dynamic date-driven heuristics once and
  distills them into a :class:`FeedSpec`.
* :class:`SpecExtractor` applies a :class:`FeedSpec` to a page, which is much
  faster than the dynamic pipeline because it uses deterministic selectors and
  restricts date parsing to only the patterns discovered during analysis.

Selector convention
--------------------
Every selector string is interpreted as follows:

* empty string ``""`` -> the item element itself;
* ``.``, ``./…``, ``..``, ``/…`` or ``(…)`` -> an XPath expression;
* anything else -> a CSS selector (via ``lxml``'s ``cssselect``).

This keeps the YAML readable while allowing a semantic-first strategy with a
positional XPath fallback.
"""

# The implementation is split by concern; this module keeps the historical
# ``newsworker.spec`` import surface intact.
from .analyze import SpecAnalysisError, SpecAnalyzer
from .execute import (
    SOURCE_ALIASES,
    SpecExtractor,
    extract_date_from_scope,
)
from .model import (
    HTML_TIME_PATTERN,
    SPEC_VERSION,
    FeedSpec,
    FieldRule,
    ItemsRule,
    SpecValidationError,
    validate_spec_dict,
)
from .selectors import (
    css_for_element,
    css_for_item_element,
    relative_selector,
    relative_xpath,
    select_nodes,
)

__all__ = [
    "HTML_TIME_PATTERN",
    "SOURCE_ALIASES",
    "SPEC_VERSION",
    "FeedSpec",
    "FieldRule",
    "ItemsRule",
    "SpecAnalysisError",
    "SpecAnalyzer",
    "SpecExtractor",
    "SpecValidationError",
    "css_for_element",
    "css_for_item_element",
    "extract_date_from_scope",
    "relative_selector",
    "relative_xpath",
    "select_nodes",
    "validate_spec_dict",
]
