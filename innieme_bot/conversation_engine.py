import asyncio
import uuid
from datetime import datetime
from .document_processor import DocumentProcessor
from .knowledge_manager import KnowledgeManager

class ConversationEngine:
    def __init__(self, document_processor:DocumentProcessor, knowledge_manager:KnowledgeManager, admin_id:str):
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
        
        # Generate context from relevant documents
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        
        # Generate response based on context and conversation history
        return await self._generate_response(context, context_messages)        
    
    async def _generate_response(self, context, history):
        """Generate a response using the context and conversation history via OpenAI API"""
        from openai import AsyncOpenAI
        import os
        
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Format conversation history into OpenAI messages format
        messages = []
        
        # Add system message with context
        system_msg = (
            "You are an experienced Assistant Scoutmaster for Scouting America, "
            "formerly known as BSA. You work as a caring coach with the scouts "
            "who are asking questions and need quick answers. Please make your answer clear, short and "
            "easy to understand, and provide official references whenever possible."
            "When you need additional information, please ask at most three times before providing your best educated answer."
        )
        print("--------- Sent to LLM ---------")
        print(f"System message: {system_msg}")
        if context:
            system_msg += (
                f"\n\nHere is some relevant information to help answer "
                f"the query:\n\n{context}"
            )
            
        messages.append({"role": "system", "content": system_msg})
        print("...(matched context)...")

        # Add conversation history
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
            print(f"{msg['role']}: {msg['content']}")
        print("------------------------------")

        try:
            # Call OpenAI API
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.1,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            return "I apologize, but I encountered an error processing your request. Please try again later."

    def is_following_thread(self, thread):
        """Check if this is a thread we should be following"""
        return thread.id in self.active_threads

