# Spec Delta

## MODIFIED Requirements

### Requirement: Freshness awareness applies on every platform
Because answers on Discord, Slack and email share one answering path, chunk labels and the freshness note SHALL appear in the model's context on all three. Only the `status` command and rescan reporting are Slack-specific.

#### Scenario: Discord answer
- **WHEN** a question is answered on Discord after a source file changed
- **THEN** the model's context carries the same labels and note as on Slack

#### Scenario: Email answer
- **WHEN** a scout's question is answered by email after a source file changed
- **THEN** the model's context carries the same labels and note as on Slack
