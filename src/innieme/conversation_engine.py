from datetime import datetime
from .document_processor import DocumentProcessor
from .knowledge_manager import KnowledgeManager
from .discord_bot_config import TopicConfig
from openai import AsyncOpenAI
import os
        

class ConversationEngine:
    def __init__(self, api_key:str, topic:TopicConfig, document_processor:DocumentProcessor, knowledge_manager:KnowledgeManager, admin_id:int):
        self.api_key = api_key
        self.topic = topic
        self.document_processor = document_processor
        self.knowledge_manager = knowledge_manager
        self.admin_id = admin_id
        self.active_threads = set()
    
    async def process_query(self, query:str, thread_id:int, context_messages:list[dict[str,str]]) -> str:
        """Process a user query and generate a response
        
        Args:
            query: The user's query text
            thread_id: Discord thread ID
            context_messages: List of previous messages in the conversation
            
        Raises:
            AssertionError: If context_messages is None
        """
        assert context_messages is not None, "context_messages cannot be None"
        self.active_threads.add(thread_id)
        # Check for special commands
        if "outie please" == query.lower():
            return f"<@{self.admin_id}> Your consultation has been requested in this thread."
        
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
        print("--------- Sent to LLM ---------")
        print(f"System message: {system_msg}")
        # Generate context from relevant documents
        context = "\n\n".join([doc.page_content for doc in relevant_docs])        
        system_msg += (
            f"\n\nHere is some relevant information to help answer the query:"
            f"\n\n{context}"
        )            
        messages.append({"role": "system", "content": system_msg})
        print(f"...(matched {len(relevant_docs)} as context)...")

        # Add conversation history
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
            print(f"{msg['role']}: {msg['content']}")
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
            print(f"Error calling OpenAI API: {str(e)}")
            response = "I apologize, but I encountered an error processing your request. Please try again later."
        print("--------- Response -----------")
        print(response)
        print("------------------------------")
        return response

    def is_following_thread(self, thread) -> bool:
        """Check if this is a thread we should be following"""
        return thread.id in self.active_threads

