"""Central configuration loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: Literal["development", "production"] = "development"
    secret_key: str = Field(default="change-me", min_length=16)
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://queueguard:queueguard@localhost:5432/queueguard"
    sync_database_url: str = "postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard"

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # SQS
    sqs_webhook_queue_url: str = "http://localhost:4566/000000000000/queueguard-events"
    sqs_dlq_url: str = "http://localhost:4566/000000000000/queueguard-events-dlq"

    # LocalStack (empty string = use real AWS)
    localstack_endpoint: str = "http://localhost:4566"

    # Delivery behaviour
    max_retry_attempts: int = 5
    initial_retry_delay_seconds: int = 30
    delivery_timeout_seconds: int = 10

    # LLM (optional)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def is_local(self) -> bool:
        return bool(self.localstack_endpoint)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
