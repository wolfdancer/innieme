import os
from pydantic import BaseModel, field_validator

class DiscordBotConfig(BaseModel):
    discord_token: str
    outie_id: int
    guild_id: int
    channel_id: int
    docs_dir: str
    
    @field_validator('discord_token')
    def token_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Discord token cannot be empty')
        return v
    
    @field_validator('outie_id', 'guild_id', 'channel_id')
    def ids_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f'ID value must be positive, got: {v}')
        return v
    
    @field_validator('docs_dir')
    def docs_dir_must_exist(cls, v):
        if not os.path.exists(v):
            raise ValueError(f'Documents directory does not exist: {v}')
        return v
