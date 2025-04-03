import asyncio
import uuid
from datetime import datetime

class ConversationEngine:
    def __init__(self, document_processor, knowledge_manager, admin_id):
        self.document_processor = document_processor
        self.knowledge_manager = knowledge_manager
        self.admin_id = admin_id
        self.active_threads = set()
    
    async def process_query(self, query, thread_id, context_messages=None):
        """Process a user query and generate a response"""
        self.active_threads.add(thread_id)
        # Check for special commands
        if "outie please" == query.lower():
            return f"<@{self.admin_id}> Your consultation has been requested in this thread."
        
        # Search for relevant document chunks
        relevant_docs = await self.document_processor.search_documents(query)
        
        # Generate context from relevant documents
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        
        # Use provided context messages or create a new one with just the current query
        messages_to_use = context_messages or [{
            "role": "user",
            "content": query,
            "timestamp": datetime.now().isoformat()
        }]
        
        # Generate response based on context and conversation history
        response = await self._generate_response(context, messages_to_use)
        
        return response
    
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
        
        if context:
            system_msg += (
                f"\n\nHere is some relevant information to help answer "
                f"the query:\n\n{context}"
            )
            
        messages.append({"role": "system", "content": system_msg})
        
        # Add conversation history
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
            
        try:
            # Call OpenAI API
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            return "I apologize, but I encountered an error processing your request. Please try again later."

    def is_following_thread(self, thread):
        """Check if this is a thread we should be following"""
        return thread.id in self.active_threads

