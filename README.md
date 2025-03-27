# innieme
Something fun to help with DRY

# Requirements
## Primary Functions
- Scan and vectorize documents from a specified directory
- Connect to Discord as a bot (alias: "innieme-duan")
- Monitor specific channels for mentions
- Provide context-aware responses using document knowledge
- Support thread-based conversations

## User Interaction Flow
- Bot is activated when a user mentions its handle
- Responses are provided in the thread where it was mentioned
- New messages in the channel create new chat sessions via threads
- Users can request admin consultation with "please consult outie"
- Admin can request thread summary with "summary and file" command

## Admin Features
- One designated admin user for manual consultation
- Admin can review threads when requested
- Admin can approve summaries for knowledge base storage
- Summaries are stored to enhance the bot's knowledge base

# Components
## Document Processing System
- Document scanner
- Text extraction module
- Vector embedding generator
- Vector database for storage

## Discord Interface
- Bot authentication and connection
- Message listener
- Thread manager
- Mention detector

## Conversation Engine
- Context manager (tracking threads as sessions)
- Query processor
- Response generator
- Admin notification system

## Knowledge Management
- Summarization engine
- Knowledge base updater
- Vector search capability

## Integration Layer
- Component coordinator
- Error handling
- Configuration manager