"""Request-scoped extraction state and keyed single-flight coordination."""

from __future__ import annotations

import contextlib
import datetime as dt
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")

_DATE_MEMO_LIMIT = 4096


@dataclass
class ExtractionContext:
    """Mutable state belonging to one logical feed build.

    Extractors may be shared, but this object must not be shared between builds.
    The qddate parsers are borrowed lazily from a per-thread cache because
    construction is relatively costly and not every strategy needs them.
    """

    source: str = "network"
    base_url: str | None = None
    default_timezone: str = "UTC"
    clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)
    debug: dict[str, Any] = field(default_factory=dict)
    response_meta: dict[str, Any] = field(default_factory=dict)
    content_language: str | None = None
    diagnostics: Any = None
    session: dict[str, Any] | None = None
    logger: Any = field(default=None, repr=False)
    #: qddate code of the page language (see :func:`newsworker.dates.qddate_language`).
    date_language: str | None = None
    #: The page language tag as written (``en-US``); decides ambiguous date order.
    date_locale: str | None = None
    #: ``"dmy"``/``"mdy"``: read ambiguous numeric dates in this order.
    date_order: str | None = None
    #: qddate pattern keys matching is narrowed to; see :meth:`narrowed_dates`.
    date_patterns: list[str] | None = None
    _date_parser: Any = field(default=None, repr=False)
    _date_parsers: list[tuple[str | None, Any]] | None = field(default=None, repr=False)
    #: Parsers with an open qddate session: ``id(parser) -> (parser, keys)``.
    _date_sessions: dict[int, tuple[Any, tuple[str, ...]]] = field(default_factory=dict, repr=False)
    #: qddate results by text and matching state; extraction reads most date
    #: nodes several times (clusters, item blocks, annotations).
    _date_memo: dict[tuple[Any, ...], Any] = field(default_factory=dict, repr=False)

    def date_memo(self) -> dict[tuple[Any, ...], Any]:
        """The store for this build's qddate results, keyed by the extractor."""
        if len(self._date_memo) >= _DATE_MEMO_LIMIT:
            # A context that outlives one build (plain library use) stays bounded.
            self._date_memo.clear()
        return self._date_memo

    @property
    def date_parser(self) -> Any:
        """The general parser, which knows every language qddate supports."""
        if self._date_parser is None:
            from .dates import thread_date_parser

            self._date_parser = thread_date_parser()
        return self._date_parser

    def set_date_language(self, language: str | None) -> None:
        """Match the page's dates with ``language``'s parser first (a qddate code)."""
        if language == self.date_language:
            return
        self._end_date_sessions()
        self.date_language = language
        self._date_parsers = None

    def date_parsers(self) -> list[tuple[str | None, Any]]:
        """``(language, parser)`` pairs in matching order, narrowed to :attr:`date_patterns`.

        The page language's parser comes first when the language is known; the
        general parser (language ``None``) always comes last.
        """
        if self._date_parsers is None:
            parsers: list[tuple[str | None, Any]] = []
            if self.date_language:
                from .dates import thread_date_parser

                parsers.append((self.date_language, thread_date_parser(self.date_language)))
            parsers.append((None, self.date_parser))
            self._date_parsers = parsers
        self._sync_date_sessions(start=True)
        return self._date_parsers

    @contextlib.contextmanager
    def narrowed_dates(self, patterns: list[str] | None) -> Iterator[None]:
        """Match only ``patterns`` (qddate keys) inside the block, with every parser.

        ``None`` keeps the full pattern set. The parsers are shared by the
        thread, so the previous state is restored on exit, even on error.
        """
        previous = self.date_patterns
        self.date_patterns = list(patterns) if patterns is not None else None
        self._sync_date_sessions(start=False)
        try:
            yield
        finally:
            self.date_patterns = previous
            self._sync_date_sessions(start=False)

    @contextlib.contextmanager
    def ordered_dates(self, order: str | None) -> Iterator[None]:
        """Read ambiguous numeric dates as ``order`` (``"dmy"``/``"mdy"``) inside the block."""
        previous = self.date_order
        self.date_order = order
        try:
            yield
        finally:
            self.date_order = previous

    def _sync_date_sessions(self, *, start: bool) -> None:
        # Sessions that no longer apply end at once. Starting one is costly
        # (qddate filters and indexes its patterns), so it waits until the
        # parser is asked for: remembered results often make that unnecessary.
        wanted = tuple(self.date_patterns) if self.date_patterns is not None else None
        for _language, parser in self._date_parsers or []:
            open_keys = self._date_sessions.get(id(parser), (None, None))[1]
            if open_keys == wanted:
                continue
            if open_keys is not None:
                parser.end_session()
                del self._date_sessions[id(parser)]
            if wanted is not None and start:
                parser.start_session(list(wanted))
                self._date_sessions[id(parser)] = (parser, wanted)

    def _end_date_sessions(self) -> None:
        for parser, _keys in self._date_sessions.values():
            parser.end_session()
        self._date_sessions.clear()

    def close(self) -> None:
        """Release request-local references promptly after a feed build."""
        self._end_date_sessions()
        self.session = None
        self._date_parser = None
        self._date_parsers = None
        self._date_memo.clear()
        self.logger = None

    def metadata_get(self, key: str, default: Any = None) -> Any:
        if self.diagnostics is None:
            return default
        return self.diagnostics.metadata.get(key, default)


@dataclass
class _Flight:
    condition: threading.Condition
    running: bool = True
    waiters: int = 0
    value: Any = None
    error: BaseException | None = None


class SingleFlight:
    """Coalesce concurrent work for the same key without serializing other keys."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: dict[str, _Flight] = {}

    def call(self, key: str, function: Callable[[], T]) -> T:
        leader = False
        with self._lock:
            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight(threading.Condition(self._lock))
                self._flights[key] = flight
                leader = True
            else:
                flight.waiters += 1
                while flight.running:
                    flight.condition.wait()
                flight.waiters -= 1
                if flight.error is not None:
                    if flight.waiters == 0:
                        self._flights.pop(key, None)
                    raise flight.error
                value = flight.value
                if flight.waiters == 0:
                    self._flights.pop(key, None)
                return value

        if leader:
            try:
                value = function()
            except BaseException as exc:
                with self._lock:
                    flight.error = exc
                    flight.running = False
                    flight.condition.notify_all()
                    if flight.waiters == 0:
                        self._flights.pop(key, None)
                raise
            with self._lock:
                flight.value = value
                flight.running = False
                flight.condition.notify_all()
                if flight.waiters == 0:
                    self._flights.pop(key, None)
            return value
        raise RuntimeError("unreachable single-flight state")

    @property
    def active_keys(self) -> int:
        with self._lock:
            return len(self._flights)


@contextlib.contextmanager
def closing_context(context: ExtractionContext) -> Iterator[ExtractionContext]:
    try:
        yield context
    finally:
        context.close()
