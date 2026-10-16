## ADDED Requirements
### Requirement: Extraction Corpus Gate
CI SHALL score extraction against a labelled corpus of at least 200 stored pages
(precision, recall, F1, title and date accuracy) at a fixed extraction time, fail on
any regression, and publish the score in the job summary. A scheduled network smoke
job SHALL check that a set of live news pages still extract.

#### Scenario: Change breaks one site
- **WHEN** a change makes any corpus case lose an expected item
- **THEN** the corpus job SHALL fail and name the case
