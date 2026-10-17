## ADDED Requirements
### Requirement: Browser Preview Form
`GET /` with `Accept: text/html` SHALL serve a script-free form that previews the
items of a submitted page and shows its subscription URL, under the same URL
validation, worker limit and rate limit as `/feed`. Other clients SHALL receive
the plain-text usage help. When API tokens are configured the form SHALL require
one; when only a signing key is configured, signed links SHALL be shown to
loopback clients only.

#### Scenario: Visitor on a server with a signing key
- **WHEN** a remote client opens `/?url=https://example.org/news`
- **AND** the server has a `feed_signing_key` but no API tokens
- **THEN** the page SHALL NOT build a feed or show a signed link

#### Scenario: Page title with markup
- **WHEN** an item title contains `<script>`
- **THEN** the preview SHALL show it as escaped text
