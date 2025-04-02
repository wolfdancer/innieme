import asyncio
import uuid
from datetime import datetime

class ConversationEngine:
    def __init__(self, document_processor, knowledge_manager, admin_id):
        self.document_processor = document_processor
        self.knowledge_manager = knowledge_manager
        self.admin_id = admin_id
        self.active_threads = {}  # Maps thread_id to conversation history
    
    async def process_query(self, query, user_id, thread_id):
        """Process a user query and generate a response"""
        # Initialize conversation history for new threads
        if thread_id not in self.active_threads:
            self.active_threads[thread_id] = []
        
        # Add user message to conversation history
        self.active_threads[thread_id].append({
            "role": "user",
            "content": query,
            "timestamp": datetime.now().isoformat()
        })
        
        # Check for special commands
        if "please consult outie" in query.lower():
            return f"I've requested consultation from the admin. They'll review this thread soon."
        
        # Search for relevant document chunks
        relevant_docs = await self.document_processor.search_documents(query)
        
        # Generate context from relevant documents
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        
        # Generate response based on context and conversation history
        response = await self._generate_response(query, context, self.active_threads[thread_id])
        
        # Add bot response to conversation history
        self.active_threads[thread_id].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now().isoformat()
        })
        
        return response
    
    async def _generate_response(self, query, context, history):
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
            "who are asking these questions. Please make your answer clear and "
            "easy to understand, and provide official references whenever possible."
        )
        
        if context:
            system_msg += (
                f"\n\nHere is some relevant information to help answer "
                f"the query:\n\n{context}"
            )
            
        messages.append({"role": "system", "content": system_msg})
        
        # Add conversation history (last 5 messages)
        for msg in history[-5:]:
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
        
    async def get_thread_history(self, thread_id):
        """Get the conversation history for a specific thread"""
        if thread_id in self.active_threads:
            return self.active_threads[thread_id]
        return []