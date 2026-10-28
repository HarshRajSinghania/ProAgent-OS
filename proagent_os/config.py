from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROAGENT_", env_file=".env", extra="ignore")

    admin_key: str = "dev-admin-key"
    db_path: str = "./data/proagent.db"
    llm_provider: str = "mock"  # mock | openai
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    host: str = "0.0.0.0"
    port: int = 8080
    skills_dirs: str = "./skills,./verticals/example/skills"
    agents_config: str = "./config/agents.yaml"
    fixtures_dir: str = "./fixtures"

    @property
    def skills_dir_list(self) -> List[Path]:
        return [Path(p.strip()) for p in self.skills_dirs.split(",") if p.strip()]

    @property
    def db_path_resolved(self) -> Path:
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
