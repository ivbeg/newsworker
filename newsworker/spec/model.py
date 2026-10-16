"""The serialisable spec (YAML) and its schema validation."""

from dataclasses import dataclass, field
from typing import Any

import yaml
from lxml import etree

from .selectors import _is_xpath

SPEC_VERSION = 1
HTML_TIME_PATTERN = "html:time"


# ---------------------------------------------------------------------------
# Spec data structures
# ---------------------------------------------------------------------------


@dataclass
class FieldRule:
    """Rule describing how to extract a single field from an item element."""

    selector: str = ""
    source: str = "text"  # text | tail | content | attr:<name>
    absolute: bool = False  # resolve value as an absolute URL
    patterns: list[str] | None = None  # qddate pattern keys (date field only)
    required: bool = False

    def to_dict(self):
        data: dict[str, Any] = {"selector": self.selector, "source": self.source}
        if self.absolute:
            data["absolute"] = True
        if self.patterns is not None:
            data["patterns"] = list(self.patterns)
        if self.required:
            data["required"] = True
        return data

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return None
        return cls(
            selector=data.get("selector", ""),
            source=data.get("source", "text"),
            absolute=bool(data.get("absolute", False)),
            patterns=data.get("patterns"),
            required=bool(data.get("required", False)),
        )


@dataclass
class ItemsRule:
    """Rule describing how to locate repeating news item elements."""

    selector: str = "./*"
    selector_type: str = "css"  # css | xpath (informational; auto-detected too)
    container: str | None = None
    stride: int = 1
    #: ``"siblings"``: each matched node starts an item that also takes the
    #: following siblings up to the next match (flat, wrapper-less listings).
    group: str | None = None

    def to_dict(self):
        data: dict[str, Any] = {
            "selector_type": self.selector_type,
            "selector": self.selector,
        }
        if self.container:
            data["container"] = self.container
        if self.stride and self.stride != 1:
            data["stride"] = self.stride
        if self.group:
            data["group"] = self.group
        return data

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            selector=data.get("selector", "./*"),
            selector_type=data.get("selector_type", "css"),
            container=data.get("container"),
            stride=int(data.get("stride", 1) or 1),
            group=data.get("group"),
        )


@dataclass
class FeedSpec:
    """Full serializable parsing specification for a site layout."""

    source_url: str | None = None
    analyzed_at: str | None = None
    title: str | None = None
    language: str = "en"
    items: ItemsRule = field(default_factory=ItemsRule)
    fields: dict = field(default_factory=dict)  # name -> FieldRule
    version: int = SPEC_VERSION
    input_kind: str = "network"

    def to_dict(self):
        return {
            "version": self.version,
            "source": {
                "url": self.source_url,
                "analyzed_at": self.analyzed_at,
                "input_kind": self.input_kind,
            },
            "feed": {
                "title": self.title,
                "language": self.language,
            },
            "items": self.items.to_dict(),
            "fields": {name: rule.to_dict() for name, rule in self.fields.items()},
        }

    def to_yaml(self):
        return yaml.safe_dump(
            self.to_dict(), sort_keys=False, allow_unicode=True, default_flow_style=False
        )

    @classmethod
    def from_dict(cls, data):
        validate_spec_dict(data)
        source = data.get("source", {}) or {}
        feed = data.get("feed", {}) or {}
        fields = {}
        for name, raw in (data.get("fields", {}) or {}).items():
            rule = FieldRule.from_dict(raw)
            if rule is not None:
                fields[name] = rule
        return cls(
            source_url=source.get("url"),
            analyzed_at=source.get("analyzed_at"),
            title=feed.get("title"),
            language=feed.get("language", "en"),
            items=ItemsRule.from_dict(data.get("items")),
            fields=fields,
            version=int(data.get("version", SPEC_VERSION)),
            input_kind=source.get("input_kind", "network"),
        )

    @classmethod
    def from_yaml(cls, text):
        return cls.from_dict(yaml.safe_load(text) or {})

    def save(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_yaml())

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as handle:
            return cls.from_yaml(handle.read())

    def validate(self):
        """Validate this spec and return it for fluent library use."""
        validate_spec_dict(self.to_dict())
        return self


class SpecValidationError(ValueError):
    """A parsing-spec schema error with a precise configuration path."""

    def __init__(self, path, message):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def validate_spec_dict(data):
    """Validate a serialized parsing spec without fetching its source."""
    if not isinstance(data, dict):
        raise SpecValidationError("$", "spec root must be a mapping")
    raw_version = data.get("version", SPEC_VERSION)
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise SpecValidationError("version", "must be an integer") from exc
    if version != SPEC_VERSION:
        raise SpecValidationError(
            "version",
            f"unsupported spec version {version}; migrate to version {SPEC_VERSION}",
        )
    items = data.get("items", {}) or {}
    if not isinstance(items, dict):
        raise SpecValidationError("items", "must be a mapping")
    selector_type = items.get("selector_type", "css")
    if selector_type not in {"css", "xpath"}:
        raise SpecValidationError("items.selector_type", "must be 'css' or 'xpath'")
    selector = items.get("selector", "./*")
    if not isinstance(selector, str) or not selector.strip():
        raise SpecValidationError("items.selector", "must be a non-empty string")
    _validate_selector("items.selector", selector)
    container = items.get("container")
    if container is not None:
        if not isinstance(container, str) or not container.strip():
            raise SpecValidationError("items.container", "must be a non-empty string")
        _validate_selector("items.container", container)
    try:
        stride = int(items.get("stride", 1))
    except (TypeError, ValueError) as exc:
        raise SpecValidationError("items.stride", "must be an integer") from exc
    if stride < 1:
        raise SpecValidationError("items.stride", "must be at least 1")
    if items.get("group") not in (None, "siblings"):
        raise SpecValidationError("items.group", "must be 'siblings' when set")
    fields = data.get("fields", {}) or {}
    if not isinstance(fields, dict):
        raise SpecValidationError("fields", "must be a mapping")
    valid_sources = {"text", "tail", "href", "src", "datetime", "content"}
    for name, rule in fields.items():
        path = f"fields.{name}"
        if not isinstance(rule, dict):
            raise SpecValidationError(path, "must be a mapping")
        field_selector = rule.get("selector", "")
        if not isinstance(field_selector, str):
            raise SpecValidationError(path + ".selector", "must be a string")
        if field_selector:
            _validate_selector(path + ".selector", field_selector)
        source = rule.get("source", "text")
        if source not in valid_sources and not (
            isinstance(source, str) and source.startswith("attr:") and source[5:]
        ):
            raise SpecValidationError(path + ".source", f"must be one of {sorted(valid_sources)}")
        for boolean_name in ("absolute", "required"):
            if boolean_name in rule and not isinstance(rule[boolean_name], bool):
                raise SpecValidationError(path + "." + boolean_name, "must be boolean")
        patterns = rule.get("patterns")
        if patterns is not None and not (
            isinstance(patterns, list) and all(isinstance(item, str) for item in patterns)
        ):
            raise SpecValidationError(path + ".patterns", "must be a list of pattern keys")
    return True


def _validate_selector(path, selector):
    try:
        if _is_xpath(selector):
            etree.XPath(selector)
        else:
            from lxml.cssselect import CSSSelector

            CSSSelector(selector)
    except Exception as exc:
        raise SpecValidationError(path, f"invalid selector: {exc}") from exc
