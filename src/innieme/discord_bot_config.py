import os, yaml
from typing import List

from pydantic import BaseModel, field_validator, model_validator

class ChannelConfig(BaseModel):
    guild_id: int
    channel_id: int
    topic: 'TopicConfig' = None  # type: ignore

class TopicConfig(BaseModel):
    name: str
    role: str
    docs_dir: str
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
    
    @model_validator(mode='after')
    def set_back_references(self):
        for topic in self.topics:
            topic.outie = self
        return self

class DiscordBotConfig(BaseModel):
    discord_token: str
    openai_api_key: str
    embedding_model: str
    outies: List[OutieConfig]

    @field_validator('discord_token')
    def token_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Discord token cannot be empty')
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
