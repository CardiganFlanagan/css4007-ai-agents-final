from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import openai

from .config import Settings

log = logging.getLogger("defensecoach.llm")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(Exception):
    pass


class LLMUnavailableError(LLMError):
    pass


class LLMRequestError(LLMError):
    pass


class LLMClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse: ...


TRANSIENT_ERRORS = (openai.APITimeoutError, openai.APIConnectionError,
                    openai.RateLimitError, openai.InternalServerError)
PERMANENT_ERRORS = (openai.AuthenticationError, openai.PermissionDeniedError,
                    openai.NotFoundError, openai.BadRequestError)


class OpenAICompatibleClient:
    def __init__(self, settings: Settings, sdk: Any | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.sdk = sdk or openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                                        timeout=settings.timeout_s, max_retries=0)
        self.sleep = sleep

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self.settings.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        attempts = self.settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                raw = self.sdk.chat.completions.create(**kwargs)
            except PERMANENT_ERRORS as exc:
                log.error("LLM permanent error: %s", type(exc).__name__)
                raise LLMRequestError(_permanent_message(exc)) from exc
            except TRANSIENT_ERRORS as exc:
                log.warning("LLM attempt %d/%d failed: %s", attempt, attempts, type(exc).__name__)
                if attempt == attempts:
                    raise LLMUnavailableError(
                        "The model service is not responding right now "
                        f"({type(exc).__name__}). Try again in a minute.") from exc
                self.sleep(2 ** (attempt - 1))
                continue
            log.info("LLM ok in %.2fs (attempt %d)", time.monotonic() - started, attempt)
            return parse_response(raw)
        raise AssertionError("unreachable")


def _permanent_message(exc: Exception) -> str:
    if isinstance(exc, openai.AuthenticationError):
        return "The API key was rejected. Check LLM_API_KEY in .env."
    if isinstance(exc, openai.NotFoundError):
        return "Model not found. Check LLM_MODEL in .env."
    if isinstance(exc, openai.PermissionDeniedError):
        return "Access denied by the provider (region or account restriction)."
    return f"The provider rejected the request: {type(exc).__name__}."


def parse_response(raw: Any) -> LLMResponse:
    if not getattr(raw, "choices", None):
        raise LLMError("The model returned an empty response.")
    msg = raw.choices[0].message
    calls: list[ToolCall] = []
    for tc in msg.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            raise LLMError(f"The model sent invalid JSON arguments for tool '{tc.function.name}'.") from exc
        if not isinstance(args, dict):
            raise LLMError(f"Tool '{tc.function.name}' arguments must be a JSON object.")
        calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
    text = (msg.content or "").strip() or None
    if text is None and not calls:
        raise LLMError("The model returned neither text nor a tool call.")
    return LLMResponse(text=text, tool_calls=calls)


class MockClient:
    def __init__(self, script: list[LLMResponse | Exception] | None = None):
        self.script = list(script or [])
        self.calls: list[dict] = []

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.script:
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return LLMResponse(text=f"[mock] I received: {last_user[:80]}")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(settings: Settings) -> LLMClient:
    if settings.provider == "mock":
        return MockClient()
    return OpenAICompatibleClient(settings)
