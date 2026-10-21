## ADDED Requirements

### Requirement: Page Language Date Matching
Dates SHALL be matched first with the qddate patterns of the page language and
the patterns without words (numeric dates). The page language SHALL be the
explicit language override, else the page metadata (`<html lang>`, the
`content-language` meta tag, `og:locale`, `<meta name="language">`), else the
`Content-Language` response header, mapped to qddate's code (`cs` is `cz`).
Text containing letters that those patterns do not read SHALL be matched again
with every qddate language. Without a page language qddate knows, every
language SHALL be used. Pattern restrictions (spec date `patterns`, cached
patterns) SHALL apply to every parser used for the page and SHALL be lifted
when the build ends, also on error.

#### Scenario: Russian page
- **WHEN** a page declares `<html lang="ru">` and shows `5 мая 2022`
- **THEN** the date SHALL be read by the Russian patterns without consulting the other languages

#### Scenario: Wrong page metadata
- **WHEN** a page declares `<html lang="de">` and shows `29 July 2022`
- **THEN** the item publication date SHALL be 29 July 2022

#### Scenario: Numeric date on a non-English page
- **WHEN** a Russian page shows `05/13/2022`
- **THEN** the date SHALL be read as 13 May 2022 without consulting the other languages

#### Scenario: Build fails during a pattern session
- **WHEN** an extraction restricted to cached patterns raises an error
- **THEN** later extractions on the same thread SHALL use the full pattern set
