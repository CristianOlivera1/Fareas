from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Fareas API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:4200"
    FRONTEND_DIST_DIR: str = ""
    FRONTEND_BASE_URL: str = "http://localhost:4200"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fareas"
    FAREAS_TEST_DB: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fareas_test"

    JWT_SECRET_KEY: str = "clave-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, gt=0)

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

    ALLOWED_EMAIL_DOMAIN: str = "unamba.edu.pe"

    R2_ENABLED: bool = False
    R2_ACCOUNT_ID: str = ""
    R2_BUCKET_NAME: str = "fareas-assets"
    R2_ENDPOINT_URL: str = ""
    R2_REGION: str = "auto"
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_PRESIGN_EXPIRE_SECONDS: int = 900
    R2_MAX_UPLOAD_MB: int = 10
    AVATAR_URL_EXPIRE_SECONDS: int = 43200
    AVATAR_MAX_UPLOAD_MB: int = 5

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

@lru_cache
def get_settings() -> Settings:
    return Settings()
