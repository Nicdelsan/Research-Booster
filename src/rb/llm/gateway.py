"""Gateway dei modelli: indipendenza dal fornitore e instradamento in base alla classificazione del dato.

Principio "i dati restano del ricercatore": un dato 'controlled' non lascia mai l'infrastruttura del
cliente; se nessun modello ammesso è configurato, la chiamata fallisce invece di degradare in silenzio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

import httpx

from rb.config import Settings


class Classification(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    CONTROLLED = 3

    @classmethod
    def parse(cls, value: str | Classification) -> Classification:
        if isinstance(value, Classification):
            return value
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"Classificazione sconosciuta: {value}") from exc


class PolicyViolation(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, prompt: str, *, max_tokens: int = 1024) -> str: ...


class OfflineProvider:
    """Fornitore deterministico per sviluppo e test: non chiama alcun servizio."""

    name = "offline"

    def complete(self, system: str, prompt: str, *, max_tokens: int = 1024) -> str:
        head = " ".join(prompt.split())[:200]
        return f"[offline] Nessun modello configurato. Richiesta ricevuta: {head}"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None, base_url: str = "https://api.anthropic.com",
                 timeout: float = 120.0):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, prompt: str, *, max_tokens: int = 1024) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY non impostata.")
        resp = httpx.post(
            f"{self.base_url}/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")


class OpenAICompatibleProvider:
    """Modelli open-weight self-hosted (per esempio dietro vLLM) con API compatibile OpenAI."""

    name = "local"

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv("RB_LOCAL_LLM_KEY", "")
        self.timeout = timeout

    def complete(self, system: str, prompt: str, *, max_tokens: int = 1024) -> str:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        resp = httpx.post(
            f"{self.base_url}/chat/completions", headers=headers, timeout=self.timeout,
            json={"model": self.model, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


@dataclass(frozen=True)
class Route:
    provider: LLMProvider
    max_classification: Classification
    location: str  # local | eu | us
    zero_retention: bool

    def describe(self) -> dict:
        return {"provider": self.provider.name, "location": self.location, "zero_retention": self.zero_retention,
                "max_classification": self.max_classification.name.lower()}


class Gateway:
    """Le rotte sono in ordine di preferenza: si usa la prima che ammette la classificazione richiesta."""

    def __init__(self, routes: list[Route]):
        self.routes = routes

    def route_for(self, classification: str | Classification) -> Route:
        level = Classification.parse(classification)
        for route in self.routes:
            if level <= route.max_classification:
                return route
        raise PolicyViolation(
            f"Nessun modello configurato può ricevere dati '{level.name.lower()}'. "
            "Configurare un modello locale o riclassificare il dato."
        )

    def complete(self, classification: str | Classification, system: str, prompt: str,
                 *, max_tokens: int = 1024) -> tuple[str, dict]:
        route = self.route_for(classification)
        return route.provider.complete(system, prompt, max_tokens=max_tokens), route.describe()


def default_gateway(settings: Settings) -> Gateway:
    enabled = [p.strip() for p in settings.llm_providers.split(",") if p.strip()]
    routes: list[Route] = []
    if "anthropic" in enabled:
        max_cls = Classification.parse(os.getenv("RB_ANTHROPIC_MAX_CLASSIFICATION", "internal"))
        routes.append(Route(AnthropicProvider(settings.anthropic_model), max_cls, "us", zero_retention=True))
    if "local" in enabled:
        routes.append(Route(OpenAICompatibleProvider(settings.local_llm_url, settings.local_llm_model),
                            Classification.CONTROLLED, "local", zero_retention=True))
    if "offline" in enabled or not routes:
        routes.append(Route(OfflineProvider(), Classification.CONTROLLED, "local", zero_retention=True))
    return Gateway(routes)
