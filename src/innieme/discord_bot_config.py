import os
from typing import List, Dict
from pydantic import BaseModel, field_validator

class ChannelConfig(BaseModel):
    guild_id: int
    channel_id: int

class TopicConfig(BaseModel):
    name: str
    role: str
    docs_dir: str
    channels: List[ChannelConfig]

    @field_validator('docs_dir')
    def docs_dir_must_exist(cls, v):
        if not os.path.exists(v):
            raise ValueError(f'Document directory does not exist: {v}')
        return v

class OutieConfig(BaseModel):
    outie_id: int
    topics: List[TopicConfig]

    @field_validator('outie_id')
    def id_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f'ID value must be positive, got: {v}')
        return v

class DiscordBotConfig(BaseModel):
    discord_token: str
    openai_api_key: str
    outies: List[OutieConfig]
    
    @field_validator('discord_token')
    def token_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Discord token cannot be empty')
        return v
