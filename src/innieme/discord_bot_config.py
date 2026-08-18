import math
import os, yaml
from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator

class ChannelConfig(BaseModel):
    guild_id: int
    channel_id: int
    topic: 'TopicConfig' = None  # type: ignore

class TopicConfig(BaseModel):
    name: str
    role: str
    docs_dir: str
    # Filename patterns to skip when scanning this topic's docs_dir. Matched
    # against both the filename and the docs_dir-relative path. Unset uses the
    # defaults (see DEFAULT_DOCS_EXCLUDE); an explicit [] scans everything.
    docs_exclude: Optional[List[str]] = None
    channels: List[ChannelConfig]
    outie: 'OutieConfig' = None  # type: ignore

    @classmethod
    @field_validator('docs_dir')
    def docs_dir_must_exist(cls, v):
        if not os.path.exists(v):
            raise ValueError(f'Document directory does not exist: {v}')
        return v
    
    @model_validator(mode='after')
    def set_back_references(self):
        for channel in self.channels:
            channel.topic = self
        return self

class OutieConfig(BaseModel):
    outie_id: int
    topics: List[TopicConfig]
    bot: 'DiscordBotConfig' = None  # type: ignore

    @field_validator('outie_id')
    def id_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f'ID value must be positive, got: {v}')
        return v
    
    @model_validator(mode='before')
    @classmethod
    def reject_misplaced_docs_exclude(cls, data):
        # Unknown keys are ignored at every level, so an outie-level
        # docs_exclude would load cleanly and exclude nothing.
        if isinstance(data, dict) and 'docs_exclude' in data:
            raise ValueError(
                'docs_exclude is a per-topic setting. Move it under the topic '
                "entry, alongside that topic's docs_dir."
            )
        return data

    @model_validator(mode='after')
    def set_back_references(self):
        for topic in self.topics:
            topic.outie = self
        return self

class DiscordBotConfig(BaseModel):
    discord_token: str
    embeddings_api_key: str
    llm_api_key: str
    embedding_model: str
    llm_model: str = "openai:gpt-5.6-terra"
    # Where downloaded embedding models are cached. Only used by the
    # "huggingface" backend. Supports "~". Defaults to a .cache directory
    # inside each topic's docs_dir when unset.
    cache_dir: Optional[str] = None
    # Embedding model name. Backend-specific; when unset each backend uses its
    # own default (OpenAI: text-embedding-3-small, HuggingFace: all-MiniLM-L6-v2).
    embeddings_model_name: Optional[str] = None
    # How many document chunks to send as context per query. Higher values
    # improve recall at the cost of more input tokens.
    retrieval_top_k: int = 5
    # Optional relevance floor (0..1). When set, chunks scoring below it are
    # dropped, so weak matches don't pad the context out to retrieval_top_k.
    retrieval_score_threshold: Optional[float] = None
    outies: List[OutieConfig]

    @field_validator('discord_token')
    def token_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Discord token cannot be empty')
        return v

    @model_validator(mode='before')
    @classmethod
    def reject_misplaced_docs_exclude(cls, data):
        # Pydantic ignores unknown top-level keys, so a docs_exclude left here
        # would parse cleanly and silently do nothing -- the excluded file
        # would be ingested anyway with no error to explain why.
        if isinstance(data, dict) and 'docs_exclude' in data:
            raise ValueError(
                'docs_exclude is a per-topic setting, not a bot-level one. '
                'Move it under the topic entry, alongside that topic\'s docs_dir.'
            )
        return data

    @field_validator('retrieval_top_k')
    def top_k_must_be_positive(cls, v):
        # Reaches the vector store as `k`; a non-positive value fails at query
        # time, so the bot would start fine and then break on the first
        # question. Catch it at load.
        if v < 1:
            raise ValueError(f'retrieval_top_k must be at least 1, got {v}')
        return v

    @field_validator('retrieval_score_threshold')
    def threshold_must_be_a_fraction(cls, v):
        # Out-of-range or NaN silently drops every chunk, so the bot answers
        # "not in the documents" for everything -- the worst failure mode
        # because it looks like a knowledge-base problem, not a config error.
        if v is None:
            return v
        if math.isnan(v):
            raise ValueError('retrieval_score_threshold must be a number, got NaN')
        if not 0 <= v <= 1:
            raise ValueError(
                f'retrieval_score_threshold must be between 0 and 1, got {v}'
            )
        return v

    @field_validator('embedding_model')
    def model_must_be_supported(cls, v):
        supported_models = ['openai', 'huggingface', 'fake']
        if v not in supported_models:
            raise ValueError(f'Unsupported embedding model: {v}')
        return v
    
    @model_validator(mode='after')
    def set_back_references(self):
        for outie in self.outies:
            outie.bot = self
        return self
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> "DiscordBotConfig":
        config_data = yaml.safe_load(yaml_content)
        return cls(**config_data)
