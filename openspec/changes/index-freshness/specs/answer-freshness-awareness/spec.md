# Spec Delta

## Purpose

Defines how index freshness is conveyed to the model that answers questions, so answers can flag material that may be out of date instead of presenting it as current.

## ADDED Requirements

### Requirement: Changed sources are labelled in the model's context
When a retrieved excerpt comes from a file that was modified or removed after it was indexed, the excerpt's source label SHALL state that it has changed since it was indexed. Excerpts from unchanged files SHALL keep their ordinary label.

#### Scenario: Excerpt from a modified file
- **GIVEN** a file edited after the last scan
- **WHEN** an excerpt from that file is retrieved for a question
- **THEN** its label marks it as changed since it was indexed

#### Scenario: Excerpt from an unchanged file
- **WHEN** an excerpt from an unchanged file is retrieved
- **THEN** its label is the plain source label

### Requirement: Index build time and change count are provided to the model
The context for each answer SHALL include when the index was last built and, when the index is stale, how many files have changed since, as counts only. When the index is current it SHALL say that no source file has changed. Before any scan, nothing SHALL be added.

#### Scenario: Stale index
- **WHEN** two files have changed since the scan and a question is answered
- **THEN** the model's context states the build time and that two files changed since

#### Scenario: File names withheld
- **WHEN** the note is added to the model's context
- **THEN** it names no files, only counts

### Requirement: The model is directed to flag possible staleness
When files have changed since indexing, the model's context SHALL direct it to say so when that could affect the answer, and to suggest a rescan, rather than present affected excerpts as current. A new file's contents SHALL be described as absent from the index.

#### Scenario: Answer depends on a changed note
- **WHEN** an answer relies on an excerpt labelled as changed since indexing
- **THEN** the model has been told to say the information may be out of date and to suggest a rescan

### Requirement: Freshness failures do not block answers
If freshness cannot be determined while answering a question, the question SHALL still be answered, without freshness information.

#### Scenario: Notes directory unavailable
- **WHEN** the staleness check raises an error during a question
- **THEN** the answer is produced from the indexed excerpts with no freshness labels or note
