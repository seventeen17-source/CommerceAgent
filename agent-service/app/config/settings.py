"""Agent Service 配置。

对标 Java 侧：这里相当于 Spring Boot 的 `@ConfigurationProperties` + `application.yml`，
由 pydantic-settings 负责读取环境变量并做类型校验；缺字段或类型不对会在启动时报错，
而不是在运行到一半时才拿到 None。

配置来源优先级：进程环境变量 > `agent-service/.env`（该文件被 gitignore）。
这里把 `.env` 路径固定为 `agent-service/.env`，避免从仓库根目录、IDE 或其他工作目录
启动进程时因为当前工作目录变化而读错配置文件。仓库根目录的 `.env` 主要给 Docker Compose
使用，不会被 Java/Spring Boot 或本模块自动共享读取。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_AGENT_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_AGENT_ENV_FILE = _AGENT_SERVICE_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_AGENT_ENV_FILE,
        env_file_encoding="utf-8",
        # 该 .env 若包含额外变量，必须忽略而不是报错。
        extra="ignore",
        # pydantic v2 默认保护 "model_" 前缀，而 MODEL_NAME / MODEL_PROVIDER
        # 正是本项目的配置项，必须显式放开。
        protected_namespaces=(),
    )

    # ---- 应用 ----
    app_name: str = "agent-service"
    environment: Literal["dev", "test", "eval", "prod"] = "dev"
    log_level: str = "INFO"

    # ---- 数据库：agent / policy schema（对 commerce.* 无任何权限）----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "commerceagent"
    agent_app_user: str = "agent_app"
    agent_app_password: str = "agent_app_dev_only"

    # ---- Java 业务后端：Agent 访问权威业务状态的唯一通道 ----
    commerce_api_base_url: str = "http://localhost:8080"
    commerce_api_timeout_seconds: float = 5.0

    # ---- 模型供应商（research.md 决策 15：不写死供应商，但先支持一个 OpenAI-compatible）----
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    model_temperature: float = 0.0

    @property
    def agent_database_url(self) -> str:
        """构造 psycopg 使用的连接串（agent / policy schema 的属主身份）。"""
        return (
            f"postgresql://{self.agent_app_user}:{self.agent_app_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """进程内单例，避免每次调用都重新读取环境变量。"""
    return Settings()
