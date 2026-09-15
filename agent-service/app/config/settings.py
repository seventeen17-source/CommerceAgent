from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMMERCE_AGENT_", case_sensitive=False)

    app_name: str = "commerceagent-agent-service"
    environment: str = "dev"
    database_dsn: str = "postgresql://commerceagent:commerceagent@localhost:5432/commerceagent"
    commerce_backend_url: str = "http://localhost:8080/api/v1"
    jwt_secret: str = Field(default="dev-only-change-me-please-32-bytes", min_length=24)
    jwt_issuer: str = "commerceagent-local"
    max_agent_steps: int = Field(default=12, ge=1, le=50)
    max_tool_retries: int = Field(default=1, ge=0, le=5)
    request_timeout_seconds: float = Field(default=5.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
