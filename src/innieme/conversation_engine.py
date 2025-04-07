from .document_processor import DocumentProcessor
from .knowledge_manager import KnowledgeManager
from .discord_bot_config import TopicConfig
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

class ConversationEngine:
    def __init__(self, api_key:str, topic:TopicConfig, document_processor:DocumentProcessor, knowledge_manager:KnowledgeManager):
        self.api_key = api_key
        self.topic = topic
        self.outie_id = topic.outie.outie_id
        self.document_processor = document_processor
        self.knowledge_manager = knowledge_manager

    async def process_query(self, query:str, context_messages:list[dict[str,str]]) -> str:
        """Process a user query and generate a response
        
        Args:
            query: The user's query text
            context_messages: List of previous messages in the conversation
            
        Raises:
            AssertionError: If context_messages is None
        """
        assert context_messages is not None, "context_messages cannot be None"
        # Check for special commands
        if "outie please" == query.lower():
            return f"<@{self.outie_id}> Your consultation has been requested in this thread."
        
        # Search for relevant document chunks
        relevant_docs = await self.document_processor.search_documents(query)
        
        # Generate response based on relevant docs and conversation history
        return await self._generate_response(relevant_docs, context_messages)

    async def _generate_response(self, relevant_docs, history) -> str:
        """Generate a response using the relevant documents and conversation history via OpenAI API
        
        Args:
            relevant_docs: List of relevant document chunks from document processor
            history: List of previous conversation messages
        """
        client = AsyncOpenAI(api_key=self.api_key)
        
        # Format conversation history into OpenAI messages format
        messages = []
        
        # Add system message with context
        system_msg = self.topic.role
        logger.debug("--------- Sent to LLM ---------")
        logger.debug(f"System message: {system_msg}")
        # Generate context from relevant documents
        context = "\n\n".join([doc.page_content for doc in relevant_docs])        
        system_msg += (
            f"\n\nHere is some relevant information to help answer the query:"
            f"\n\n{context}"
        )            
        messages.append({"role": "system", "content": system_msg})
        logger.debug(f"...(matched {len(relevant_docs)} as context)...")

        # Add conversation history
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
            logger.debug(f"{msg['role']}: {msg['content']}")
        response = ""
        try:
            # Call OpenAI API
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.1,
                max_tokens=1000
            )
            
            response = response.choices[0].message.content or "I got an empty response. Please try again."
            
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {str(e)}")
            response = "I apologize, but I encountered an error processing your request. Please try again later."
        logger.debug("--------- Response -----------")
        logger.debug(response)
        logger.debug("------------------------------")
        return response