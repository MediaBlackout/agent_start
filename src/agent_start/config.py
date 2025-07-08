"""Application configuration."""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///memory.db"
    weather_ua: str = "MediaBlackoutWeatherBot/0.1 (matt@mediablackout.ai)"
    log_level: str = "INFO"

    class Config:
        env_prefix = "WA_"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
