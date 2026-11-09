# Spec Delta

## Purpose

Lets scouts ask a topic's knowledge base questions by email, answering only when the outie and one of the scout's own guardians are copied, so an adult sees every exchange.

## ADDED Requirements

### Requirement: Each topic polls its own mailbox
Each topic SHALL have exactly one mailbox. The bot SHALL check every topic's mailbox for messages when it starts and then every `poll_interval_seconds` (default 300). Mail in a topic's mailbox SHALL be answered from that topic's documents only.

#### Scenario: Periodic check
- **GIVEN** `poll_interval_seconds` is unset
- **WHEN** a message arrives in a topic's mailbox
- **THEN** it is handled within about five minutes, using that topic's documents

#### Scenario: Mailbox unreachable
- **WHEN** a mailbox cannot be reached or rejects the login
- **THEN** the error is logged, other topics' mailboxes are still checked, and the next poll tries again

### Requirement: Handled messages are deleted from the server
Once a message has been handled, including sending any reply it calls for, the bot SHALL delete it from the server permanently. A message whose handling fails SHALL be left on the server and tried again on the next poll, except that a reply permanently refused by the mail server is not retried until the bot restarts. The bot SHALL keep no copy of messages outside the mailbox.

#### Scenario: Answered question
- **WHEN** a scout's question is answered
- **THEN** the question is deleted from the mailbox after the answer is sent

#### Scenario: Handling fails
- **WHEN** the model or the outgoing mail server fails while handling a message
- **THEN** no reply is sent, the message stays on the server, and it is handled again on the next poll

#### Scenario: A recipient is refused
- **WHEN** the outgoing mail server refuses any one of a reply's recipients
- **THEN** the reply is sent to none of them, and the message stays on the server

#### Scenario: A recipient is permanently refused
- **GIVEN** the mail server permanently rejects a guardian's address
- **WHEN** the following polls run
- **THEN** the message is not answered again until the bot restarts, and is deleted once past retention

### Requirement: Messages past retention are deleted
Any message still on the server that reached the mailbox more than `retention_days` ago (default 30) SHALL be deleted without a reply, and its sender and subject logged.

#### Scenario: Sender's clock is wrong
- **GIVEN** a scout's device dates their message 40 days in the past
- **WHEN** the message arrives
- **THEN** it is handled normally, because its age is measured from when it reached the mailbox

#### Scenario: Message that keeps failing
- **GIVEN** a message has failed on every poll for 31 days
- **WHEN** the next poll runs with the default retention
- **THEN** the message is deleted without a reply

### Requirement: Auto-generated mail is deleted without reply
A message SHALL be treated as auto-generated when it has an `Auto-Submitted` header other than `no`, an `X-Autoreply`, `X-Autorespond` or `X-Auto-Response-Suppress` header, `Precedence` of `bulk`, `list` or `junk`, a `List-Id` or `List-Unsubscribe` header, an empty return path, or is a delivery status report. Such mail SHALL be deleted without a reply, whoever sent it.

#### Scenario: Scout's out-of-office reply
- **WHEN** a scout's out-of-office reply to a bot answer arrives
- **THEN** it is deleted, nothing is sent, and the event is logged

#### Scenario: Bounce of a bot reply
- **WHEN** a delivery failure report for one of the bot's replies arrives
- **THEN** it is deleted and logged as a warning naming the failed recipient where it can be read

### Requirement: Mail from unknown senders is deleted without reply
A message whose sender is not the topic's outie, one of its scouts, or a guardian of one of its scouts SHALL be deleted without a reply, and its sender logged.

#### Scenario: Stranger writes in
- **WHEN** an address not in the topic's configuration sends a question
- **THEN** no reply is sent, the message is deleted, and the sender is logged

### Requirement: Outie mail is not answered
A message from the topic's outie SHALL be deleted without a reply. The outie copies the bot so that their answer is part of the thread's quoted history.

#### Scenario: Outie replies to a scout
- **WHEN** the outie replies to a scout and copies the bot
- **THEN** the bot sends nothing and deletes the message

### Requirement: Guardians receive a one-time setup note
A message from a guardian SHALL be answered with a setup note explaining that the bot answers scouts who copy the outie and one of their guardians, unless the guardian's message is a reply in a chain that already contains a setup note from the bot; such a message is deleted without a reply.

#### Scenario: Guardian asks a question
- **WHEN** a guardian emails the bot, not in reply to a setup note
- **THEN** they receive the setup note and no answer to the question

#### Scenario: Guardian replies to the setup note
- **GIVEN** the bot sent a guardian a setup note
- **WHEN** the guardian replies to it
- **THEN** nothing is sent

### Requirement: Scouts are answered only with the outie and their own guardian copied
A message from a scout SHALL be answered from the topic's documents only when the outie's address and at least one of that scout's own guardians appear in `To` or `Cc`. A guardian of a different scout SHALL NOT count.

#### Scenario: Rule met
- **WHEN** a scout sends a question with the outie and their mother in Cc
- **THEN** the bot answers the question

#### Scenario: Another scout's guardian
- **WHEN** a scout copies the outie and a guardian listed only for a different scout
- **THEN** the question is not answered and the rule reminder applies

### Requirement: Scouts who break the rule receive a one-time reminder
When a scout's message does not meet the copy rule, the bot SHALL reply with a reminder of the rule that names that scout's guardians, unless the scout's message is a reply in a chain that already contains a reminder from the bot; such a message is deleted without a reply.

#### Scenario: Outie missing
- **WHEN** a scout copies their guardian but not the outie
- **THEN** the scout receives the reminder naming their guardians, and the question is not answered

#### Scenario: Second miss replying to the reminder
- **GIVEN** a scout received a reminder
- **WHEN** the scout replies to it, again without the outie
- **THEN** nothing is sent

### Requirement: Earlier bot replies are found in the reply chain
Whether a message's reply chain already contains a setup note, reminder or answer from the bot SHALL be determined from its `References` and `In-Reply-To` headers, which carry the IDs of the bot's earlier replies. It SHALL NOT depend on state kept by the bot. A message that does not reply to the bot's note, such as a second reply to the same original email, carries no trace of it and is treated as the first in its chain.

#### Scenario: Restart between messages
- **GIVEN** the bot sent a reminder, then restarted
- **WHEN** the scout replies to the reminder still without the outie
- **THEN** no second reminder is sent

#### Scenario: Two replies to the same original
- **GIVEN** a scout sent two separate replies to the same earlier email, neither copying the outie
- **WHEN** both are handled
- **THEN** each receives a reminder, because neither replies to the other's reminder

#### Scenario: Reminder kept in the chain after an answer
- **GIVEN** a scout received a reminder, then replied to it correctly and was answered
- **WHEN** the scout replies to that answer without the outie
- **THEN** no reminder is sent, because the answer's `References` still carries the reminder

### Requirement: The question and its context are read from the message
The bot SHALL use the plain-text part of a message, or its HTML part converted to markdown when there is no plain-text part. The newly written text SHALL be the question and the quoted earlier messages SHALL be given to the model as conversation history, in the order they were written. When no quoted part can be found, the whole body SHALL be the question. Signatures SHALL be removed.

#### Scenario: Reply with quoted history
- **WHEN** a scout replies above the quoted previous answer
- **THEN** the model receives the new text as the question and the quoted answer as history

#### Scenario: One quoted answer
- **WHEN** a scout's reply quotes a single earlier bot answer
- **THEN** the model's conversation history contains that answer

#### Scenario: HTML-only message
- **WHEN** a message has only an HTML part containing a bulleted list
- **THEN** the question reaches the model as markdown with the list preserved

### Requirement: Message size sent to the model is capped
The text taken from a message SHALL be limited to a fixed maximum before it reaches the model, keeping the newest text and dropping the oldest quoted history first.

#### Scenario: Long forwarded chain
- **WHEN** a scout's message quotes a very long chain
- **THEN** the question and the most recent history are kept and older history is dropped

### Requirement: Attachments are not read
Attachments SHALL NOT be read or passed to the model. When an answered message had attachments, the answer SHALL say that attachments cannot be read.

#### Scenario: Question with a PDF attached
- **WHEN** a scout asks about an attached PDF
- **THEN** the answer is based on the text and documents only and states that the attachment was not read

### Requirement: Replies are addressed only to configured people
Every reply SHALL be addressed `To` the sender. An answer SHALL also `Cc` the outie and those of the scout's guardians who were on the scout's message. No other address from the incoming message SHALL receive a reply.

#### Scenario: Extra person copied
- **WHEN** a scout copies the outie, their father and a friend
- **THEN** the answer goes to the scout, Cc the outie and the father, and not to the friend

### Requirement: Replies thread and identify as automatic
Every reply SHALL use the subject `Re: <original subject>` (without stacking `Re:`), set `In-Reply-To` and `References` so mail clients thread it, set `Auto-Submitted: auto-replied`, and carry both a plain-text and an HTML body.

#### Scenario: Answer appears in thread
- **WHEN** the bot answers a message with subject "Re: Campout gear"
- **THEN** the answer's subject is "Re: Campout gear" and it appears in the same thread in the scout's mail client

### Requirement: Configuration is validated at startup
The email configuration SHALL fail to load when a scout has no guardians, when an address is listed both as a scout and as a guardian in the same topic, or when a topic's mailbox address is also its outie, a scout or a guardian. The error SHALL name the offending address.

#### Scenario: Scout without guardians
- **WHEN** the config lists a scout with an empty guardians list
- **THEN** the bot refuses to start and the error names that scout
