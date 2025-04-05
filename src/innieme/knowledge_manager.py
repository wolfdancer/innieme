import asyncio
import json
import os
from datetime import datetime

class KnowledgeManager:
    def __init__(self, summaries_path="./data/summaries"):
        self.summaries_path = summaries_path
        self.pending_summaries = {}  # Maps thread_id to generated summary
        
        # Create summaries directory if it doesn't exist
        os.makedirs(self.summaries_path, exist_ok=True)
    
    async def generate_summary(self, thread_id):
        """Generate a summary for a conversation thread"""
        # In a real implementation, this would use an LLM to summarize
        # For this example, we'll use a placeholder
        
        # Placeholder summary
        summary = f"This is a summary of the conversation in thread {thread_id}. " \
                 f"It contains key points discussed and important information " \
                 f"that could be useful for future reference."
        
        # Store pending summary
        self.pending_summaries[thread_id] = {
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
        return summary
    
    async def store_summary(self, thread_id):
        """Store an approved summary in the knowledge base"""
        if thread_id not in self.pending_summaries:
            return False
        
        summary_data = self.pending_summaries[thread_id]
        
        # Create a unique filename for the summary
        filename = f"summary_{thread_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = os.path.join(self.summaries_path, filename)
        
        # Save summary to file
        with open(file_path, 'w') as f:
            json.dump(summary_data, f)
        
        # Remove from pending summaries
        del self.pending_summaries[thread_id]
        
        return True
    
    async def load_summaries(self):
        """Load all stored summaries"""
        summaries = []
        
        for filename in os.listdir(self.summaries_path):
            if filename.endswith('.json'):
                file_path = os.path.join(self.summaries_path, filename)
                try:
                    with open(file_path, 'r') as f:
                        summary_data = json.load(f)
                        summaries.append(summary_data)
                except Exception as e:
                    print(f"Error loading summary {filename}: {str(e)}")
        
        return summaries