from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def parse_cors_allowed_origins(value: str | None) -> list[str]:
    if value is None:
        value = DEFAULT_CORS_ALLOWED_ORIGINS
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    mexc_base_url: str = Field(default="https://api.mexc.com", alias="MEXC_BASE_URL")
    app_env: str = Field(default="development", alias="APP_ENV")
    secret_key: SecretStr = Field(alias="SECRET_KEY")
    api_key_encryption_key: SecretStr = Field(alias="API_KEY_ENCRYPTION_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_review_model: str = Field(default="gpt-4o-mini", alias="OPENAI_REVIEW_MODEL")
    mexc_access_key: SecretStr | None = Field(default=None, alias="MEXC_ACCESS_KEY")
    mexc_secret_key: SecretStr | None = Field(default=None, alias="MEXC_SECRET_KEY")
    cors_allowed_origins: str = Field(
        default=DEFAULT_CORS_ALLOWED_ORIGINS,
        alias="CORS_ALLOWED_ORIGINS",
    )

    @property
    def parsed_cors_allowed_origins(self) -> list[str]:
        return parse_cors_allowed_origins(self.cors_allowed_origins)

    @field_validator("openai_api_key", "mexc_access_key", "mexc_secret_key", mode="before")
    @classmethod
    def empty_secret_to_none(cls, value: object) -> object:
        return None if value == "" else value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
