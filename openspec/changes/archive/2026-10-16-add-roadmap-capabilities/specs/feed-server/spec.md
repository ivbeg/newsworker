## ADDED Requirements
### Requirement: Signed Feed Links
When `feed_signing_key` is configured, `GET /feed` SHALL require either a valid API
token or a `sig` parameter equal to the HMAC-SHA256 of the requested format and
source URL. A signature SHALL authorise only that exact URL and format.

#### Scenario: Reader uses a signed link
- **WHEN** a feed reader requests `/feed?url=U&format=rss&sig=S` with a valid `S` and no API token
- **THEN** the server SHALL serve the feed

#### Scenario: Signature reused for another source
- **WHEN** the same `sig` is sent with a different `url`
- **THEN** the server SHALL answer 401

### Requirement: Public Subscription URLs
`newsworker feed-url URL` SHALL print the subscription URL for a source, using
`public_base_url` when set and signing it when a signing key is configured. Feed
self links SHALL use the same URL and SHALL NOT contain API tokens.

#### Scenario: Server behind a reverse proxy
- **WHEN** `public_base_url` is `https://feeds.example.org` and a signing key is set
- **THEN** `feed-url` SHALL print `https://feeds.example.org/feed?url=...&format=rss&sig=...`
