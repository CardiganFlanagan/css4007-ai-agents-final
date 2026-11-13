from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
}
SUPPORTED_PROVIDERS = {*PROVIDER_BASE_URLS, "mock"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    model: str
    base_url: str | None
    timeout_s: float = 30.0
    max_retries: int = 2

    def __repr__(self) -> str:
        return (f"Settings(provider={self.provider!r}, model={self.model!r}, "
                f"base_url={self.base_url!r}, api_key='***')")


def load_settings(env: dict[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = dict(os.environ)

    provider = env.get("LLM_PROVIDER", "openai").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigError(
            f"Unknown LLM_PROVIDER '{provider}'. Use one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}")

    api_key = env.get("LLM_API_KEY", "").strip()
    model = env.get("LLM_MODEL", "").strip()
    if provider != "mock":
        if not api_key:
            raise ConfigError("LLM_API_KEY is empty. Copy .env.example to .env and add your key.")
        if not model:
            raise ConfigError("LLM_MODEL is empty. Set it in .env (see .env.example).")

    try:
        timeout_s = float(env.get("LLM_TIMEOUT_S", "30"))
        max_retries = int(env.get("LLM_MAX_RETRIES", "2"))
    except ValueError as exc:
        raise ConfigError(f"LLM_TIMEOUT_S / LLM_MAX_RETRIES must be numbers: {exc}") from exc
    if timeout_s <= 0 or not 0 <= max_retries <= 5:
        raise ConfigError("LLM_TIMEOUT_S must be > 0 and LLM_MAX_RETRIES between 0 and 5.")

    base_url = env.get("LLM_BASE_URL") or PROVIDER_BASE_URLS.get(provider)
    return Settings(provider, api_key, model or "mock-model", base_url, timeout_s, max_retries)
