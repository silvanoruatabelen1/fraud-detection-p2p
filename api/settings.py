from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{ROOT / 'fraud.db'}"
    artifacts_dir: Path = ROOT / "artifacts"
    demo_data_dir: Path = ROOT / "data" / "demo"
    seed_on_startup: bool = True
    cors_origins: str = "*"


settings = Settings()
