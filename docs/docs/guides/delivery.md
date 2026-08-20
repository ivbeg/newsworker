---
title: "Watch delivery"
description: "Outbox guarantees and stdout, webhook, SMTP, and Telegram channels"
---

# Watch delivery guarantees and channels

Watch contacts upstream on every tick and uses conditional validators, even
while the ordinary content TTL is fresh. A `304` is a successful unchanged
observation.

Items enter a SQLite outbox scoped by feed, item identity, channel, and
destination. Delivery is acknowledged only after that destination reports
success. Pending/retry state survives restart, and due records from an earlier
run are processed before new discoveries. Delivered rows are retained for the
configured period and then pruned. Delivery is at least once: receivers should
honor the stable `Idempotency-Key` webhook header to suppress a duplicate after
an ambiguous timeout.

Built-in channel implementations are:

- `stdout`: acknowledges after the write and flush complete.
- `webhook`: bounded JSON HTTP POST with a stable idempotency key.
- `smtp`: stdlib SMTP/TLS with message-size and connection limits.
- `telegram`: Telegram Bot API via the shared destination policy.

Third-party packages may register deterministic channels in the
`newsworker.delivery` entry-point group. Channels classify an attempt as
success, retryable, or terminal; retry scheduling remains centralized in the
outbox. Credentials are resolved from configuration and are never written into
the outbox payload.

Select one or more destinations by repeating `--channel`:

```bash
newsworker watch https://example.com/news --channel webhook \
  --webhook https://hooks.example/news
newsworker watch https://example.com/news --channel smtp \
  --smtp-recipient alerts@example.com
newsworker watch https://example.com/news --channel telegram \
  --telegram-chat-id 123456
newsworker watch https://example.com/news --channel smtp --channel telegram \
  --smtp-recipient alerts@example.com --telegram-chat-id 123456
```

SMTP host, port, sender, username, and password and the Telegram bot token come
from the layered settings (`NEWSWORKER_SMTP_*` and `NEWSWORKER_TELEGRAM_TOKEN`).
A configured channel is validated before the first poll. Webhook destination
identities are hashed before persistence so query-string credentials never enter
the outbox.

See [`watch`](/commands/watch) and [runtime configuration](/guides/runtime-configuration).
