# slack-bot-commands Specification

## Purpose
Defines the commands given to the Slack bot by mentioning it, who may run them, and what they report about the document index. Only behavior touched by index freshness is specified here.

## Requirements

### Requirement: Status command reports index state
Mentioning the bot with the single word `status` in a channel configured for a topic SHALL reply in a thread with the time of the last scan and how long ago it was, the scan duration split into reading and indexing, the chunk and file counts, the number of files that could not be read, and the index's freshness as of that moment. A message that merely contains the word, such as a question, SHALL NOT be treated as the command.

#### Scenario: Status after a scan
- **WHEN** someone mentions the bot with `status`
- **THEN** the reply gives the last scan time, its age, duration, chunk and file counts, and freshness

#### Scenario: Status before any scan
- **WHEN** `status` is requested and no scan has completed
- **THEN** the reply says that no scan has completed yet

#### Scenario: Question containing the word
- **WHEN** someone asks "what is the status of Northwind?"
- **THEN** it is answered as a question, not run as a command

#### Scenario: Freshness unavailable
- **WHEN** the freshness check raises an error or does not finish in time
- **THEN** the reply still gives the scan details and counts, and its freshness line says freshness could not be determined

#### Scenario: Status report cannot be produced
- **WHEN** the report itself fails for any other reason
- **THEN** the reply says the status could not be checked and points to the bot logs, without file paths or error text

### Requirement: Status is open to everyone; file names are private to the outie
`status` SHALL be available to any channel member. The `status` reply posted in the channel SHALL contain counts only, whoever asked; it SHALL NOT list file names. When the requester is the topic's outie, the file names SHALL be sent in a separate message visible only to the outie, and SHALL NOT appear in channel history or in the conversation history later given to the model. Names SHALL be rendered so they cannot be interpreted as Slack markup or mentions.

#### Scenario: Non-outie requester
- **GIVEN** two files changed since the scan
- **WHEN** a non-outie requests `status`
- **THEN** the channel reply reports two changed files and names none, and no private message is sent

#### Scenario: Outie requester
- **WHEN** the outie requests `status`
- **THEN** the channel reply has counts only, and a message visible only to the outie names the modified, new and removed files and any files that could not be read

#### Scenario: Names never reach later model context
- **WHEN** the outie has requested `status` and a later question in that thread is answered
- **THEN** the conversation history given to the model contains no file names from the private message

#### Scenario: Private delivery fails
- **WHEN** the private message to the outie cannot be sent
- **THEN** the counts-only channel reply is still posted and the names are not posted publicly

#### Scenario: Hostile file name
- **WHEN** a listed file name contains `<`, `>`, `&` or a backtick
- **THEN** it is shown exactly as written, with no character altered, and is not interpreted as markup or a mention

### Requirement: Rescan is open to everyone and reports its duration
`rescan` SHALL be available to any channel member rather than only the outie. A successful rescan's reply SHALL state that scan's own running time, excluding any time spent waiting for an earlier scan to finish. A failed rescan SHALL say it failed and that the previously loaded documents are still being used.

#### Scenario: Non-outie rescan
- **WHEN** a non-outie mentions the bot with `rescan`
- **THEN** the topic's documents are rescanned

#### Scenario: Successful rescan
- **WHEN** a rescan completes
- **THEN** the reply says the rescan is complete, how long it took, and the usual chunk and file summary

#### Scenario: Failed rescan
- **WHEN** a rescan fails
- **THEN** the reply says so, without error details, and that earlier documents are still in use

### Requirement: Quit remains outie-only
`quit` SHALL be accepted only from the topic's outie. Any other requester SHALL be told it is only available to the outie, and the bot SHALL keep running.

#### Scenario: Non-outie quit
- **WHEN** a non-outie mentions the bot with `quit`
- **THEN** the bot replies that the command is only available to the outie and does not shut down
