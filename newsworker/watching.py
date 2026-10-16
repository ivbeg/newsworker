"""One ``watch`` poll: drain due deliveries, fetch the page, deliver new items.

The CLI command (``newsworker watch``) owns scheduling, signals and exit codes;
this module owns what a single poll does, so it can be reused and tested
without the command line.
"""

import json
import logging

from .settings import Settings


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

    delivered: list = []
    failed = retried = 0
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


def run_watch_iteration(
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

    runtime_settings = getattr(service, "settings", None) or Settings()
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
                payloads.append(DeliveryPayload(item, feed or {}, key))
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

    inserted_uids: set = set()
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
