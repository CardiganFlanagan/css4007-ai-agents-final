import json
import logging
import time
from dataclasses import dataclass, field

import openai

log = logging.getLogger("defensecoach.llm")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list = field(default_factory=list)


class LLMError(Exception):
    pass


class LLMUnavailableError(LLMError):
    pass


class LLMRequestError(LLMError):
    pass


TEMPORARY_ERRORS = (openai.APITimeoutError, openai.APIConnectionError,
                    openai.RateLimitError, openai.InternalServerError)
PERMANENT_ERRORS = (openai.AuthenticationError, openai.PermissionDeniedError,
                    openai.NotFoundError, openai.BadRequestError)


class OpenAICompatibleClient:
    def __init__(self, settings, sdk=None, sleep=time.sleep):
        self.settings = settings
        self.sleep = sleep
        if sdk is None:
            sdk = openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                                timeout=settings.timeout, max_retries=0)
        self.sdk = sdk

    def complete(self, messages, tools=None, json_mode=False):
        request = {"model": self.settings.model, "messages": messages}
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        if json_mode:
            request["response_format"] = {"type": "json_object"}

        attempts = self.settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                raw = self.sdk.chat.completions.create(**request)
                return parse_response(raw)
            except PERMANENT_ERRORS as e:
                log.error("LLM error: %s", type(e).__name__)
                raise LLMRequestError(permanent_error_message(e))
            except TEMPORARY_ERRORS as e:
                log.warning("LLM attempt %d/%d failed: %s", attempt, attempts, type(e).__name__)
                if attempt == attempts:
                    raise LLMUnavailableError(
                        f"The model service is not responding right now ({type(e).__name__}). "
                        "Try again in a minute.")
                self.sleep(2 ** (attempt - 1))


def permanent_error_message(e):
    if isinstance(e, openai.AuthenticationError):
        return "The API key was rejected. Check LLM_API_KEY in .env."
    if isinstance(e, openai.NotFoundError):
        return "Model not found. Check LLM_MODEL in .env."
    if isinstance(e, openai.PermissionDeniedError):
        return "Access denied by the provider (region or account restriction)."
    return f"The provider rejected the request: {type(e).__name__}."


def parse_response(raw):
    if not raw.choices:
        raise LLMError("The model returned an empty response.")
    message = raw.choices[0].message

    tool_calls = []
    for call in message.tool_calls or []:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            raise LLMError(f"The model sent invalid JSON arguments for tool '{name}'.")
        if not isinstance(args, dict):
            raise LLMError(f"Tool '{name}' arguments must be a JSON object.")
        tool_calls.append(ToolCall(call.id, name, args))

    text = (message.content or "").strip()
    if not text and not tool_calls:
        raise LLMError("The model returned neither text nor a tool call.")
    return LLMResponse(text or None, tool_calls)


class MockClient:
    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.calls = []

    def complete(self, messages, tools=None, json_mode=False):
        self.calls.append({"messages": list(messages), "tools": tools, "json_mode": json_mode})
        if not self.answers:
            return LLMResponse(f"[mock] I received: {messages[-1]['content'][:80]}")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def make_client(settings):
    if settings.provider == "mock":
        return MockClient()
    return OpenAICompatibleClient(settings)
