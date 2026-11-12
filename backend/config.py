from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///./data/helpdesk.db"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=25, gt=0, le=120)
    backend_url: str = "http://127.0.0.1:8000"
    duplicate_similarity_threshold: float = Field(default=0.78, ge=0.5, le=1)
    sla_warning_hours: float = Field(default=2, gt=0, le=72)
