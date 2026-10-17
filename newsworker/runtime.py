"""Request-scoped extraction state and keyed single-flight coordination."""

from __future__ import annotations

import contextlib
import datetime as dt
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ExtractionContext:
    """Mutable state belonging to one logical feed build.

    Extractors may be shared, but this object must not be shared between builds.
    A qddate parser is created lazily because construction is relatively costly and
    not every strategy needs it.
    """

    source: str = "network"
    base_url: Optional[str] = None
    default_timezone: str = "UTC"
    clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)
    debug: Dict[str, Any] = field(default_factory=dict)
    response_meta: Dict[str, Any] = field(default_factory=dict)
    content_language: Optional[str] = None
    diagnostics: Any = None
    session: Optional[Dict[str, Any]] = None
    logger: Any = field(default=None, repr=False)
    _date_parser: Any = field(default=None, repr=False)

    @property
    def date_parser(self) -> Any:
        if self._date_parser is None:
            from qddate import DateParser

            self._date_parser = DateParser(generate=True)
        return self._date_parser

    def close(self) -> None:
        """Release request-local references promptly after a feed build."""
        self.session = None
        self._date_parser = None
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
    error: Optional[BaseException] = None


class SingleFlight:
    """Coalesce concurrent work for the same key without serializing other keys."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: Dict[str, _Flight] = {}

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
