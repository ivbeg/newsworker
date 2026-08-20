---
title: "Watch and delivery"
description: "Poll a page and deliver only new items to stdout, webhooks, SMTP, or Telegram"
---

# Watch and delivery

`watch` polls a page on an interval, tracks which items it has already seen, and
emits or delivers only new items.

```bash
newsworker watch "https://example.com/news" --interval 300
newsworker watch "https://example.com/news" --channel webhook \
  --webhook https://hooks.example/news
newsworker watch "https://example.com/news" --channel smtp \
  --smtp-recipient alerts@example.com
```

Items enter a SQLite outbox. Delivery is acknowledged only after the destination
reports success. Pending/retry state survives restart. Receivers should honor
the stable `Idempotency-Key` webhook header.

See [`watch`](/commands/watch) and [delivery](/guides/delivery).
