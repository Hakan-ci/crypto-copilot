from pydantic import SecretStr

from app.core.config import Settings


def test_settings_loads_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/app")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.delenv("MEXC_BASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MEXC_ACCESS_KEY", "")
    monkeypatch.setenv("MEXC_SECRET_KEY", "")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://user:pass@localhost:5432/app"
    assert settings.mexc_base_url == "https://contract.mexc.com"
    assert settings.app_env == "development"
    assert isinstance(settings.secret_key, SecretStr)
    assert settings.secret_key.get_secret_value() == "test-secret-key"
    assert settings.api_key_encryption_key.get_secret_value() == "test-encryption-key"
    assert settings.openai_api_key is None
    assert settings.parsed_cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_settings_loads_env_overrides(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/copilot")
    monkeypatch.setenv("MEXC_BASE_URL", "https://contract.mexc.com")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "override-secret")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", "override-encryption-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000, http://127.0.0.1:3000",
    )

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/copilot"
    assert settings.mexc_base_url == "https://contract.mexc.com"
    assert settings.app_env == "test"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "openai-test-key"
    assert settings.parsed_cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
