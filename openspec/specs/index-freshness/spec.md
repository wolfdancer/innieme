# index-freshness Specification

## Purpose
Defines what a document scan records about itself and how the resulting index is compared with its source files, so the system can state when the index was built and which files have changed since.

## Requirements

### Requirement: Scan records a snapshot
Each completed scan of a topic SHALL record when it started and finished, how long reading the documents and building the index each took, the number of chunks and indexed files, the files whose text could not be extracted, and a size and modification time for every non-excluded candidate file. A candidate that cannot be stat'ed during the scan SHALL be recorded as failed, with no stamp.

#### Scenario: Successful scan
- **WHEN** a scan of a topic completes
- **THEN** a snapshot is available that reports the scan's timing, chunk count, indexed file count, and failed files

#### Scenario: File cannot be stat'ed
- **WHEN** a candidate file cannot be stat'ed during the scan
- **THEN** it is listed among the failed files and is reported as modified, not new, by a later check that can stat it

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

#### Scenario: Extraction errors and no text
- **GIVEN** a topic with a completed snapshot
- **WHEN** a rescan hits at least one extraction error and no candidate file supplies any text, including when the other candidates are readable but empty
- **THEN** the scan fails and the earlier snapshot and index continue to be used

#### Scenario: Only empty files
- **WHEN** every candidate file is readable but contains no text and none raised an extraction error
- **THEN** the scan succeeds with zero chunks and records a snapshot, as scanning does today, since an empty file is not a failure

#### Scenario: Some files fail
- **WHEN** extraction fails for some candidates but at least one candidate supplies text
- **THEN** the scan succeeds, the failed files are listed in the snapshot, and the rest are indexed

### Requirement: Staleness is detected by comparison with the directory
The system SHALL report, for a topic with a snapshot, which files recorded in the snapshot (indexed, empty or failed alike) have a different size or modification time than recorded (modified), which candidate files were not in the snapshot (new), and which snapshot files no longer exist (removed). The check SHALL NOT read file contents.

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

#### Scenario: Empty file gains content
- **GIVEN** a readable file that contained no text when scanned
- **WHEN** it is later edited to contain text
- **THEN** it is reported as modified

#### Scenario: Failed file repaired
- **GIVEN** a file that failed text extraction during the scan
- **WHEN** it is later changed
- **THEN** it is reported as modified, since a rescan may now succeed

#### Scenario: File cannot be examined
- **WHEN** a recorded file, or any directory under the topic's documents directory, exists but cannot be read or stat'ed during the check
- **THEN** freshness is reported as unknown, not as unchanged or removed

#### Scenario: Unreadable directory the topic excludes
- **WHEN** a directory whose contents all match the topic's exclusion patterns cannot be read during the check
- **THEN** it is skipped, and freshness is still determined from the rest of the documents

#### Scenario: No snapshot
- **WHEN** the check runs before any scan has completed
- **THEN** it reports that freshness is unknown rather than reporting every file as new

### Requirement: Staleness results may be briefly reused
Routine staleness checks made while answering questions MAY reuse a result for up to 30 seconds, provided it was computed against the caller's snapshot. A check requested explicitly by a person, and the first check after a scan, SHALL reflect the directory as it is at that moment.

#### Scenario: Cached routine check
- **WHEN** a file changes within 30 seconds of a routine check
- **THEN** a second routine check may still report the earlier result

#### Scenario: Explicit check
- **WHEN** a person requests status after a file changed
- **THEN** the change is reported regardless of any earlier routine check

#### Scenario: Result from an older snapshot
- **WHEN** a rescan completes and a routine check follows
- **THEN** the check reflects the new snapshot, never a result computed for the old one

### Requirement: Routine checks do not pile up
At most one routine check per topic SHALL run at a time. A routine caller that arrives while one is running SHALL reuse its result only if it was computed for the caller's snapshot, and otherwise SHALL proceed without freshness information. A result that completes late MAY populate the reuse window.

#### Scenario: Slow check in flight
- **GIVEN** a routine check that has been running for longer than a caller is willing to wait
- **WHEN** further questions arrive
- **THEN** they do not start additional checks

#### Scenario: In-flight check belongs to an older snapshot
- **GIVEN** a routine check running against snapshot A
- **WHEN** a rescan publishes snapshot B and a question arrives holding B
- **THEN** the question does not take A's result and proceeds without freshness information

### Requirement: Explicit checks are bounded
An explicit check SHALL wait for any running check to finish and then run its own fresh check, and SHALL wait no longer than 10 seconds in total. If it cannot finish in that time or checking is unavailable, it SHALL report that freshness could not be determined.

#### Scenario: Explicit check during a routine check
- **GIVEN** a routine check in flight that inspected a file before it was edited
- **WHEN** a person requests status after the edit
- **THEN** the status check runs afresh after the routine one and reports the edit

#### Scenario: Mount hangs
- **GIVEN** a routine check stuck on an unavailable notes directory
- **WHEN** a person requests status
- **THEN** within 10 seconds the reply says freshness could not be determined, and still gives the scan details

### Requirement: Freshness is judged against the index the excerpts came from
Staleness for an answer SHALL be computed against the snapshot that belongs to the index the excerpts were retrieved from, taken together with them. A rescan completing during the answer SHALL NOT cause excerpts from the older index to be judged against the newer snapshot.

#### Scenario: Rescan completes mid-answer
- **GIVEN** excerpts retrieved from index A
- **WHEN** a rescan publishes index B before the answer's freshness is determined
- **THEN** the excerpts are judged against A's snapshot, so a file edited between A and B is still labelled changed

### Requirement: Scans of one topic do not overlap
At most one scan of a given topic SHALL run at a time; a scan requested while another is running SHALL wait for it.

#### Scenario: Concurrent rescans
- **WHEN** two rescans of the same topic are requested at once
- **THEN** the second begins only after the first finishes
