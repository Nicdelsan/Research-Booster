"""Configurazione da variabili d'ambiente (nessuna dipendenza esterna)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("RB_DATABASE_URL", "sqlite:///./research_booster.db"))
    storage_dir: str = field(default_factory=lambda: _env("RB_STORAGE_DIR", "./storage"))
    # Fornitori LLM attivi, separati da virgola: offline, anthropic, local
    llm_providers: str = field(default_factory=lambda: _env("RB_LLM_PROVIDERS", "offline"))
    anthropic_model: str = field(default_factory=lambda: _env("RB_ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    local_llm_url: str = field(default_factory=lambda: _env("RB_LOCAL_LLM_URL", "http://localhost:8001/v1"))
    local_llm_model: str = field(default_factory=lambda: _env("RB_LOCAL_LLM_MODEL", "local-model"))


def get_settings() -> Settings:
    return Settings()
