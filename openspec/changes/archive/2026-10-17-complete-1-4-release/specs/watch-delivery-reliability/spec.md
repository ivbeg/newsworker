## ADDED Requirements
### Requirement: Upgrade-safe Item Identity
When an item's identity changes because ids are now derived from links, the
outbox SHALL treat the item as already handled if its previous id (kept as
`content_hash`) is recorded in the 1.3 `seen` table or in the outbox for the same
channel and destination.

#### Scenario: First poll after upgrading from 1.3
- **WHEN** `watch` polls a page whose items were all seen by 1.3
- **THEN** no item SHALL be delivered again
