"""Configuración central del backend (12-factor: todo por variables de entorno).

Ver back-fareas/.env.example para el catálogo completo de variables.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Fareas API"
    ENVIRONMENT: str = "development"  # development | production
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:4200"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fareas"
    FAREAS_TEST_DB: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fareas_test"

    JWT_SECRET_KEY: str = "clave-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    MODELS_DIR: str = "models"
    FACE_MATCH_THRESHOLD: float = 0.75

    MAIL_ENABLED: bool = True
    MAIL_HOST: str = "smtp.gmail.com"
    MAIL_PORT: int = 587
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM_ADDRESS: str = ""
    MAIL_FROM_NAME: str = "Fareas"

    DEVICE_TOKEN_SECRET: str = "token-de-dispositivos"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
