---
title: "Runtime configuration"
description: "CLI, environment, YAML, and default precedence for newsworker settings"
---

# Runtime configuration

Newsworker resolves settings in this order, from strongest to weakest:

1. An explicitly supplied CLI option.
2. A `NEWSWORKER_*` environment variable.
3. The selected YAML configuration file.
4. The built-in dataclass default.

An omitted CLI option does not replace a configured value. Resolved settings are
validated before network, batch, watch, or server work starts and are immutable
for the lifetime of that operation.

Every public `Settings` field has an environment spelling formed by uppercasing
the field name, for example `content_ttl` becomes `NEWSWORKER_CONTENT_TTL`.
Booleans accept `true/false`, `yes/no`, `on/off`, or `1/0`. Lists accept a JSON
list or comma-separated values. Dictionaries such as `NEWSWORKER_EXTRA_HEADERS`
require a JSON object.

```bash
export NEWSWORKER_CONTENT_TTL=900
export NEWSWORKER_ALLOWED_HOSTS='news.example,feeds.example'
export NEWSWORKER_EXTRA_HEADERS='{"Accept-Language":"fr"}'
export NEWSWORKER_API_TOKENS='["replace-with-a-secret"]'
newsworker serve --host 0.0.0.0
```

Proxy credentials, API and Telegram tokens, SMTP passwords, cookie paths, and
authorization-like headers are redacted by `Settings.to_dict(redact=True)` and
by diagnostic output.

Important secure defaults include private/special-address blocking, TLS
verification, robots compliance, five validated redirect hops, disabled CORS,
and no trusted proxy. Intranet access requires both `allow_private_hosts: true`
and an explicit `allowed_hosts` entry. Set `trusted_proxy: true` only when the
configured outbound proxy is itself trusted to enforce destination policy.

Watch settings include `watch_interval`, `watch_max_pages`, `delivery_retries`,
`delivery_backoff`, and `delivered_retention_days`. Server controls include
`api_tokens`, `rate_limit_per_minute`, `rate_limit_burst`,
`max_concurrent_builds`, and `cors_allowed_origins`.

See [Settings](/guides/settings) for the YAML file and
[security](/guides/security) for fetch and server policy.
