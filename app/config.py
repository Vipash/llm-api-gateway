from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed env config. Names match .env.example; env vars win over defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/llm_gateway"
    )
    redis_url: str = "redis://localhost:6379/0"
    llm_provider_base_url: str = "http://localhost:11434/v1"
    llm_model_name: str = "llama3.2"
    openai_api_key: str | None = None
    mock_upstream: bool = False

settings = Settings()