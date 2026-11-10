from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "media-extraction-pipeline"
    APP_ENV: str = "development"
    DEBUG: bool = True
    TIMEZONE: str = "Asia/Tokyo"
    LOG_LEVEL: str = "INFO"

    # JWT 認証
    JWT_SECRET_KEY: str = "change_this_to_a_secure_random_key_for_jwt"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # PostgreSQL 基本設定 (デフォルトを "db" にしておくとDocker環境で安全)
    POSTGRES_SERVER: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str

    # Celery 用設定
    CELERY_BROKER_URL:str= "redis://redis:6379/0"
    # 外部API / LLM
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://172.17.0.1:11434"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    ENABLED_L3_ADDONS:str = ""

    @property
    def tz_info(self) -> ZoneInfo:
        """zoneinfo.ZoneInfo オブジェクトを動的に返す"""
        return ZoneInfo(self.TIMEZONE)


settings = Settings()

