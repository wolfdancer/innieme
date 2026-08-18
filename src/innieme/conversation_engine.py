from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from .document_processor import DocumentProcessor
from .knowledge_manager import KnowledgeManager
from .discord_bot_config import TopicConfig
import logging
import os

logger = logging.getLogger(__name__)


def _format_chunk(doc) -> str:
    """Render one retrieved chunk, labelled with the file it came from.

    The source filename lets the model attribute a detail to a specific
    document; without it the chunks arrive anonymously and any citation the
    model offers is a guess.
    """
    source = (doc.metadata or {}).get("source")
    if not source:
        return doc.page_content
    return f"[source: {os.path.basename(source)}]\n{doc.page_content}"


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


@dataclass
class ConversationDependencies:
    document_context: str
    conversation_history: list
    topic_role: str


def _build_system_prompt(ctx: RunContext[ConversationDependencies]) -> str:
    parts = [ctx.deps.topic_role]
    if ctx.deps.document_context:
        parts.append(
            f"Here is some relevant information to help answer the query:"
            f"\n\n{ctx.deps.document_context}"
        )
    if ctx.deps.conversation_history:
        history_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in ctx.deps.conversation_history]
        )
        parts.append(f"Conversation history:\n{history_text}")
    return "\n\n".join(parts)


class ConversationEngine:
    def __init__(
        self,
        topic: TopicConfig,
        document_processor: DocumentProcessor,
        knowledge_manager: KnowledgeManager,
        model: str = "openai:gpt-5.6-terra",
        llm_api_key: str = "",
    ):
        self.topic = topic
        self.outie_id = topic.outie.outie_id
        self.document_processor = document_processor
        self.knowledge_manager = knowledge_manager
        # How many document chunks to feed the model as context per query, and
        # an optional relevance floor so weak matches are dropped rather than
        # padding the context out to retrieval_top_k.
        self.retrieval_top_k = getattr(topic.outie.bot, "retrieval_top_k", None) or 5
        self.retrieval_score_threshold = getattr(
            topic.outie.bot, "retrieval_score_threshold", None
        )

        self.agent = Agent(
            model=_build_model(model, llm_api_key),
            deps_type=ConversationDependencies,
            instructions=_build_system_prompt,
        )

    async def process_query(self, query: str, context_messages: list[dict[str, str]]) -> str:
        """Process a user query and generate a response.

        Args:
            query: The user's query text
            context_messages: List of previous messages in the conversation

        Raises:
            AssertionError: If context_messages is None
        """
        assert context_messages is not None, "context_messages cannot be None"

        if "outie please" == query.lower():
            return f"<@{self.outie_id}> Your consultation has been requested in this thread."

        relevant_docs = await self.document_processor.search_documents(
            query,
            top_k=self.retrieval_top_k,
            score_threshold=self.retrieval_score_threshold,
        )
        return await self._generate_response(query, relevant_docs, context_messages)

    async def _generate_response(self, query: str, relevant_docs, history) -> str:
        """Generate a response using PydanticAI agent.

        Args:
            query: The current user query
            relevant_docs: List of relevant document chunks from document processor
            history: List of previous conversation messages (excluding current query)
        """
        context = "\n\n".join(_format_chunk(doc) for doc in relevant_docs)

        logger.debug("--------- Sent to LLM ---------")
        logger.debug(f"System message: {self.topic.role}")
        logger.debug(f"...(matched {len(relevant_docs)} as context)...")

        # Exclude the last message (current query) from history to avoid duplication
        prior_history = history[:-1] if history else []

        deps = ConversationDependencies(
            document_context=context,
            conversation_history=prior_history,
            topic_role=self.topic.role,
        )

        response = ""
        try:
            result = await self.agent.run(query, deps=deps)
            response = result.output
        except Exception as e:
            logger.error(f"Error calling LLM: {str(e)}")
            response = "I apologize, but I encountered an error processing your request. Please try again later."

        logger.debug("--------- Response -----------")
        logger.debug(response)
        logger.debug("------------------------------")
        return response
