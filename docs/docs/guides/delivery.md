---
title: "Watch delivery"
description: "Outbox guarantees and stdout, webhook, SMTP, Telegram, Slack, Discord and Matrix channels"
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
- `slack`: Slack incoming webhook; the title links to the item, and `<`, `>`,
  `&` are escaped so a page title cannot ping `<!channel>`.
- `discord`: Discord webhook with `allowed_mentions` disabled, so `@everyone`
  in a title is inert.
- `matrix`: a message in a Matrix room; the outbox idempotency key is the
  Matrix transaction id, so the homeserver de-duplicates a retried send.

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
newsworker watch --from-opml subscriptions.opml --channel slack --channel matrix
```

SMTP host, port, sender, username, and password and the Telegram bot token come
from the layered settings (`NEWSWORKER_SMTP_*` and `NEWSWORKER_TELEGRAM_TOKEN`).
Chat channels are configured the same way and selected with `--channel`:

```yaml
slack_webhook_url: https://hooks.slack.com/services/…     # secret
discord_webhook_url: https://discord.com/api/webhooks/…   # secret
matrix_homeserver: https://matrix.example.org
matrix_token: …                                           # secret
matrix_room: "!abcdef:example.org"
```

Webhook URLs and tokens are redacted in configuration dumps and never stored in
the outbox; Slack and Discord destinations are identified by a hash of the URL.
A configured channel is validated before the first poll. Webhook destination
identities are hashed before persistence so query-string credentials never enter
the outbox.

See [`watch`](/commands/watch) and [runtime configuration](/guides/runtime-configuration).
