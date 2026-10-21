## ADDED Requirements

### Requirement: Consistent Day and Month Order
Numeric day-month dates printed together (one date cluster, or the items one
spec selects) SHALL be read in one order. A date whose first number is above
12 SHALL make the group day-first; a date whose second number is above 12
SHALL make it month-first. When neither occurs, a page whose locale is `en-US`
SHALL be read month-first and any other page day-first. Ambiguous dates read
the other way SHALL be read again in the chosen order with qddate's
alternative pattern, keeping their time of day. A group with contradicting
dates SHALL keep each date as qddate reads it.

#### Scenario: US listing
- **WHEN** an `en-US` page lists `05/06/2022`, `05/04/2022` and `05/02/2022`
- **THEN** the items SHALL be dated 6 May, 4 May and 2 May 2022

#### Scenario: Evidence beats the locale
- **WHEN** an `en-US` page lists `13/05/2022` and `05/06/2022`
- **THEN** the items SHALL be dated 13 May and 5 June 2022

#### Scenario: Unambiguous date decides
- **WHEN** a page without a locale lists `05/13/2022` and `05/06/2022`
- **THEN** the items SHALL be dated 13 May and 6 May 2022

#### Scenario: Two-digit years
- **WHEN** a Russian page lists `05/06/22` and `04/06/22`
- **THEN** the items SHALL be dated 5 June and 4 June 2022
