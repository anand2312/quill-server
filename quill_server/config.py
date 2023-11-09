from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    USE_REDIS_SESSIONS: bool = True
    DATABASE_URL: str
    REDIS_URL: str


settings = Settings()  # type: ignore
# pylance thinks we should pass args here, but they're being loaded from .env
