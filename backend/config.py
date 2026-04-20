from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# Walk up from backend/ to find the project root .env
_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Email alerts (Gmail SMTP)
    alert_email_from: str = ""      # your Gmail address
    alert_email_password: str = ""  # Gmail App Password (not your login password)
    alert_email_to: str = ""        # family member's email

    # Database — port 5433 avoids conflict with any local Postgres on 5432
    database_url: str = "postgresql+asyncpg://aria:aria@localhost:5433/aria_db"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"       # used for background tasks (extraction, sentiment)
    ollama_chat_model: str = "llama3.2:3b"  # used for real-time call chat (speed critical)

    # App
    base_url: str = "http://localhost:8001"
    secret_key: str = "changeme"
    audio_dir: str = "./audio"

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
