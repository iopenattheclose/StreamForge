from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Server
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    # Generation limits
    max_active_generations: int = Field(default=1000, gt=0)
    queue_max_size: int = Field(default=50, gt=0)

    # Lifecycle
    generation_ttl: int = Field(default=30, gt=0)
    terminal_record_ttl: int = Field(default=300, gt=0)

    # Streaming
    backpressure_timeout: int = Field(default=30, gt=0)
    heartbeat_interval: int = Field(default=20, gt=0)
    token_delay: float = Field(default=0.05, ge=0)


settings = Settings()