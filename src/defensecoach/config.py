import os
from dataclasses import dataclass

from dotenv import load_dotenv

BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
}
PROVIDERS = ["openai", "gemini", "groq", "mock"]


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    provider: str
    api_key: str
    model: str
    base_url: str | None
    timeout: float = 30
    max_retries: int = 2

    def __repr__(self):
        return f"Settings(provider={self.provider}, model={self.model}, api_key=***)"


def load_settings(env=None):
    if env is None:
        load_dotenv()
        env = os.environ

    provider = env.get("LLM_PROVIDER", "openai").strip().lower()
    if provider not in PROVIDERS:
        raise ConfigError(f"Unknown LLM_PROVIDER '{provider}'. Use one of: {', '.join(PROVIDERS)}")

    api_key = env.get("LLM_API_KEY", "").strip()
    model = env.get("LLM_MODEL", "").strip()
    if provider != "mock" and not api_key:
        raise ConfigError("LLM_API_KEY is empty. Copy .env.example to .env and add your key.")
    if provider != "mock" and not model:
        raise ConfigError("LLM_MODEL is empty. Set it in .env.")

    try:
        timeout = float(env.get("LLM_TIMEOUT_S", "30"))
        max_retries = int(env.get("LLM_MAX_RETRIES", "2"))
    except ValueError:
        raise ConfigError("LLM_TIMEOUT_S and LLM_MAX_RETRIES must be numbers.")
    if timeout <= 0 or max_retries < 0 or max_retries > 5:
        raise ConfigError("LLM_TIMEOUT_S must be > 0 and LLM_MAX_RETRIES between 0 and 5.")

    base_url = env.get("LLM_BASE_URL") or BASE_URLS.get(provider)
    return Settings(provider, api_key, model or "mock-model", base_url, timeout, max_retries)
