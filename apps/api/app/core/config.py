from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Ignore unexpected env variables so local development environments don't crash on unrelated keys.
    # Checks both the explicit apps/api/.env path and working-directory .env
    model_config = SettingsConfigDict(env_file=(_ENV_FILE, ".env"), extra="ignore")

    # Local Ollama Provider & Embeddings
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:8b"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_think: bool = False
    embedding_dimensions: int = 768

    # RAG Retrieval Settings
    rag_top_k: int = 5
    rrf_k: int = 60
    hybrid_fetch_k: int = 20
    reranker_model: str = "ms-marco-MiniLM-L-12-v2"

    # Evaluation & LLM-as-Judge Settings
    judge_model: str = "openai:gpt-4o-mini"

    # OpenAI Provider
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    # Anthropic (Claude) Provider
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"

    # Google Gemini Provider
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com"

    # xAI (Grok) Provider
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"

    # DeepSeek Provider
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"

    # Race timeouts in seconds
    first_token_timeout_s: float = 15.0
    model_timeout_s: float = 60.0

    # Database Configuration (PostgreSQL with asyncpg on port 5433)
    database_url: str = "postgresql+asyncpg://versuslab:versuslab@localhost:5433/versuslab"

    # Coordinator Concurrency & Retries
    max_concurrent_model_calls: int = 8
    max_connection_retries: int = 2

    # Single-User Authentication & Security (Phase 10 - Disabled by default for direct access)
    admin_username: str = "admin"
    admin_password_hash: str = (
        "$argon2id$v=19$m=65536,t=3,p=4$ATMUOT3NjHGMGBi4yJ8Qjw$+N2Jdrzuej32NBq72GFqoRZnet8/RDYwBWZaphR4FCg"
    )
    jwt_secret_key: str = "versuslab-dev-jwt-secret-key-change-in-prod-must-be-long-and-secure"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    auth_enabled: bool = False

    # Request Size & In-Memory Rate Limiting
    max_upload_size_bytes: int = 5 * 1024 * 1024  # 5 Megabytes
    race_rate_limit_per_minute: int = 60
    document_rate_limit_per_minute: int = 30

    # Observability (OpenTelemetry, Prometheus & Sentry)
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "versuslab-api"
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 1.0


settings = Settings()