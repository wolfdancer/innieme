import json
import logging

from datetime import datetime
from typing import List
import os

from pydantic import BaseModel
from pydantic_ai import Agent

logger = logging.getLogger(__name__)


def _build_model(model_str: str, api_key: str):
    """Build a PydanticAI model instance from a model string and API key.

    If no api_key is provided, returns the model string as-is and lets
    pydantic-ai read the key from the appropriate environment variable.
    """
    if not api_key or ":" not in model_str:
        return model_str
    provider_name, model_name = model_str.split(":", 1)
    if provider_name == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))
    elif provider_name == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
        return AnthropicModel(model_name, provider=AnthropicProvider(api_key=api_key))
    # Unknown provider — fall back to string (env var)
    return model_str


class SummaryOutput(BaseModel):
    summary: str
    key_points: List[str]
    suggested_title: str


class KnowledgeManager:
    def __init__(self, model: str = "openai:gpt-3.5-turbo", llm_api_key: str = "", summaries_path: str = "./data/summaries"):
        self.summaries_path = summaries_path
        self.pending_summaries = {}  # Maps thread_id to generated summary data

        os.makedirs(self.summaries_path, exist_ok=True)

        self.summary_agent = Agent(
            model=_build_model(model, llm_api_key),
            output_type=SummaryOutput,
            instructions=(
                "You are a knowledge base curator. Produce concise, accurate "
                "summaries of conversations suitable for long-term storage."
            ),
        )

    async def generate_summary(self, thread_id, conversation_text: str) -> SummaryOutput:
        """Generate a structured summary for a conversation thread."""
        result = await self.summary_agent.run(conversation_text)
        summary_output: SummaryOutput = result.output

        self.pending_summaries[thread_id] = {
            "summary": summary_output.summary,
            "key_points": summary_output.key_points,
            "suggested_title": summary_output.suggested_title,
            "timestamp": datetime.now().isoformat(),
        }

        return summary_output

    async def store_summary(self, thread_id):
        """Store an approved summary in the knowledge base."""
        if thread_id not in self.pending_summaries:
            return False

        summary_data = self.pending_summaries[thread_id]

        filename = f"summary_{thread_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = os.path.join(self.summaries_path, filename)

        with open(file_path, "w") as f:
            json.dump(summary_data, f)

        del self.pending_summaries[thread_id]

        return True

    async def load_summaries(self):
        """Load all stored summaries."""
        summaries = []

        for filename in os.listdir(self.summaries_path):
            if filename.endswith(".json"):
                file_path = os.path.join(self.summaries_path, filename)
                try:
                    with open(file_path, "r") as f:
                        summary_data = json.load(f)
                        summaries.append(summary_data)
                except Exception as e:
                    logger.error(f"Error loading summary {filename}: {str(e)}")

        return summaries
