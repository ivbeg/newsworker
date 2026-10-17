"""Request-scoped extraction context and single-flight caching."""

import threading
import time

import pytest

from newsworker.runtime import ExtractionContext, SingleFlight, closing_context


def test_singleflight_coalesces_same_key_and_propagates_errors():
    flight = SingleFlight()
    barrier = threading.Barrier(5)
    calls = []

    def expensive():
        calls.append(1)
        time.sleep(0.03)
        return "value"

    results = []

    def worker():
        barrier.wait()
        results.append(flight.call("same", expensive))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == ["value"] * 5
    assert len(calls) == 1 and flight.active_keys == 0
    with pytest.raises(RuntimeError, match="boom"):
        flight.call("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    error_barrier = threading.Barrier(3)
    errors = []

    def failing():
        time.sleep(0.02)
        raise RuntimeError("shared failure")

    def error_worker():
        error_barrier.wait()
        try:
            flight.call("shared-error", failing)
        except RuntimeError as exc:
            errors.append(str(exc))

    error_threads = [threading.Thread(target=error_worker) for _ in range(2)]
    for thread in error_threads:
        thread.start()
    error_barrier.wait()
    for thread in error_threads:
        thread.join()
    assert errors == ["shared failure", "shared failure"]
    assert flight.active_keys == 0


def test_context_cleanup():
    context = ExtractionContext()
    context.session = {"debug": {}}
    with closing_context(context):
        assert context.date_parser is not None
    assert context.session is None and context._date_parser is None
