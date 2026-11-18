from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        extra="ignore",
    )

    database_url: str
    ai_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    resend_api_key: str = ""
    email_from: str = ""
    email_to: str = ""
    max_article_age_hours: int = Field(default=25, gt=0)
    top_articles_count: int = Field(default=8, gt=0)

    @field_validator("database_url")
    @classmethod
    def check_database_url(cls, value: str) -> str:
        if not value.startswith(("postgres://", "postgresql://")):
            raise ValueError("must start with postgres:// or postgresql://")
        return value

    def require_ai(self) -> None:
        if not self.ai_api_key:
            raise ValueError("AI_API_KEY is required")

    def require_email(self) -> None:
        missing = [
            name.upper()
            for name in ("resend_api_key", "email_from", "email_to")
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(f"Missing email settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()