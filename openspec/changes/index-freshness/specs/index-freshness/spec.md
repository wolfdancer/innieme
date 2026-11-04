# Spec Delta

## Purpose

Defines what a document scan records about itself and how the resulting index is compared with its source files, so the system can state when the index was built and which files have changed since.

## ADDED Requirements

### Requirement: Scan records a snapshot
Each completed scan of a topic SHALL record when it started and finished, how long reading the documents and building the index each took, the number of chunks and indexed files, the files whose text could not be extracted, and a size and modification time for every non-excluded candidate file.

#### Scenario: Successful scan
- **WHEN** a scan of a topic completes
- **THEN** a snapshot is available that reports the scan's timing, chunk count, indexed file count, and failed files

#### Scenario: No scan yet
- **WHEN** no scan of a topic has completed
- **THEN** no snapshot exists and freshness is reported as unknown

### Requirement: Snapshot reflects the text that was indexed
A file's recorded size and modification time SHALL be captured before its contents are read, so a file edited while the scan is running is reported as changed afterwards.

#### Scenario: Edit during scan
- **WHEN** a file is modified after its size and modification time were captured but before the scan completes
- **THEN** the next staleness check reports that file as modified

### Requirement: Failed scan preserves the previous index state
A scan that fails SHALL leave both the previously served index and its snapshot unchanged.

#### Scenario: Every candidate unreadable
- **GIVEN** a topic with a completed snapshot
- **WHEN** a rescan finds candidate files but can extract text from none of them
- **THEN** the scan fails and the earlier snapshot and index continue to be used

### Requirement: Staleness is detected by comparison with the directory
The system SHALL report, for a topic with a snapshot, which indexed files have a different size or modification time than recorded (modified), which candidate files were not in the snapshot (new), and which snapshot files no longer exist (removed). The check SHALL NOT read file contents.

#### Scenario: Nothing changed
- **WHEN** the staleness check runs and no candidate file differs from the snapshot
- **THEN** the index is reported as current

#### Scenario: Modified, new and removed files
- **WHEN** one indexed file is edited, one file is added, and one indexed file is deleted
- **THEN** the check reports one modified, one new and one removed file

#### Scenario: Modification time alone
- **WHEN** a file's modification time changes but its size does not
- **THEN** the file is reported as modified

#### Scenario: Excluded files
- **WHEN** a file matching the topic's exclusion patterns is created or changed
- **THEN** it is not reported as new or modified

#### Scenario: Unreadable file unchanged
- **GIVEN** a file that failed text extraction during the scan
- **WHEN** the file has not changed since the scan
- **THEN** it is not reported as stale, since rescanning would not help

#### Scenario: No snapshot
- **WHEN** the check runs before any scan has completed
- **THEN** it reports that freshness is unknown rather than reporting every file as new

### Requirement: Staleness results may be briefly reused
Routine staleness checks made while answering questions MAY reuse a result for up to 30 seconds. A check requested explicitly by a person, and the first check after a scan, SHALL reflect the directory as it is at that moment.

#### Scenario: Cached routine check
- **WHEN** a file changes within 30 seconds of a routine check
- **THEN** a second routine check may still report the earlier result

#### Scenario: Explicit check
- **WHEN** a person requests status after a file changed
- **THEN** the change is reported regardless of any earlier routine check

### Requirement: Scans of one topic do not overlap
At most one scan of a given topic SHALL run at a time; a scan requested while another is running SHALL wait for it.

#### Scenario: Concurrent rescans
- **WHEN** two rescans of the same topic are requested at once
- **THEN** the second begins only after the first finishes
