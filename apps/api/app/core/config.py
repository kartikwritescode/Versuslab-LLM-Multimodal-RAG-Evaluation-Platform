from pydantic_settings import BaseSettings , SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file = ".env",extras='ignore')
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:4b"


settings = Settings()