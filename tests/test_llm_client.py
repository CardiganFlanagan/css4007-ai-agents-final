from types import SimpleNamespace

import httpx
import openai
import pytest

from defensecoach.cli import InputError, ask_once, main
from defensecoach.config import ConfigError, load_settings
from defensecoach.llm_client import (LLMError, LLMRequestError, LLMResponse, LLMUnavailableError,
                                     MockClient, OpenAICompatibleClient, ToolCall)

REQ = httpx.Request("POST", "https://example.test/chat/completions")


def settings(**over):
    env = {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "test-key", "LLM_MODEL": "test-model",
           "LLM_MAX_RETRIES": "2", **over}
    return load_settings(env)


def fake_completion(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeSDK:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client_with(*outcomes, **over):
    sdk = FakeSDK(*outcomes)
    sleeps = []
    return OpenAICompatibleClient(settings(**over), sdk=sdk, sleep=sleeps.append), sdk, sleeps


def test_missing_api_key_gives_clear_config_error():
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        load_settings({"LLM_PROVIDER": "gemini", "LLM_MODEL": "m"})


def test_unknown_provider_rejected():
    with pytest.raises(ConfigError, match="Unknown LLM_PROVIDER"):
        load_settings({"LLM_PROVIDER": "skynet"})


@pytest.mark.parametrize("provider,url", [("openai", "api.openai.com"),
                                          ("gemini", "generativelanguage.googleapis.com"),
                                          ("groq", "api.groq.com")])
def test_provider_selects_endpoint(provider, url):
    assert url in settings(LLM_PROVIDER=provider).base_url


def test_api_key_never_appears_in_repr():
    s = settings(LLM_API_KEY="super-secret-123")
    assert "super-secret-123" not in repr(s)


def test_text_response_is_returned():
    client, sdk, _ = client_with(fake_completion("What does call_llm do on timeout?"))
    resp = client.complete([{"role": "user", "content": "quiz me"}])
    assert resp.text == "What does call_llm do on timeout?"
    assert resp.tool_calls == []
    assert sdk.requests[0]["model"] == "test-model"
    assert "tools" not in sdk.requests[0]


def test_tool_call_is_parsed_and_model_chooses_tools():
    tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="read_file", arguments='{"path": "a.py"}'))
    client, sdk, _ = client_with(fake_completion(None, [tc]))
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]
    resp = client.complete([{"role": "user", "content": "x"}], tools=tools)
    assert resp.tool_calls == [ToolCall(id="c1", name="read_file", arguments={"path": "a.py"})]
    assert sdk.requests[0]["tool_choice"] == "auto"


def test_invalid_tool_arguments_json_raises_llm_error():
    tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="read_file", arguments="{not json"))
    client, _, _ = client_with(fake_completion(None, [tc]))
    with pytest.raises(LLMError, match="invalid JSON"):
        client.complete([{"role": "user", "content": "x"}])


def test_empty_model_output_raises_llm_error():
    client, _, _ = client_with(fake_completion("   "))
    with pytest.raises(LLMError, match="neither text nor a tool call"):
        client.complete([{"role": "user", "content": "x"}])


def test_timeout_is_retried_then_succeeds():
    client, sdk, sleeps = client_with(openai.APITimeoutError(request=REQ), fake_completion("ok"))
    assert client.complete([{"role": "user", "content": "x"}]).text == "ok"
    assert len(sdk.requests) == 2
    assert sleeps == [1]


def test_rate_limit_gives_up_after_retry_budget():
    rate = lambda: openai.RateLimitError("slow down", response=httpx.Response(429, request=REQ), body=None)
    client, sdk, sleeps = client_with(rate(), rate(), rate())
    with pytest.raises(LLMUnavailableError, match="not responding"):
        client.complete([{"role": "user", "content": "x"}])
    assert len(sdk.requests) == 3
    assert sleeps == [1, 2]


def test_bad_api_key_is_not_retried():
    err = openai.AuthenticationError("bad key", response=httpx.Response(401, request=REQ), body=None)
    client, sdk, _ = client_with(err, fake_completion("never reached"))
    with pytest.raises(LLMRequestError, match="API key was rejected"):
        client.complete([{"role": "user", "content": "x"}])
    assert len(sdk.requests) == 1


def test_ask_once_sends_system_prompt_and_keeps_history():
    mock = MockClient([LLMResponse(text="Q1?"), LLMResponse(text="Q2?")])
    history = []
    assert ask_once(mock, "start", history) == "Q1?"
    assert ask_once(mock, "my answer", history) == "Q2?"
    sent = mock.calls[1]["messages"]
    assert sent[0]["role"] == "system" and "DefenseCoach" in sent[0]["content"]
    assert [m["content"] for m in sent[1:]] == ["start", "Q1?", "my answer"]


@pytest.mark.parametrize("bad", ["", "   ", "x" * 5000])
def test_invalid_user_input_is_rejected_before_calling_model(bad):
    mock = MockClient()
    with pytest.raises(InputError):
        ask_once(mock, bad)
    assert mock.calls == []


def test_cli_reports_api_failure_without_traceback(monkeypatch, capsys):
    failing = MockClient([LLMUnavailableError("The model service is not responding right now.")])
    monkeypatch.setattr("defensecoach.cli.make_client", lambda s: failing)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert main(["hello"]) == 1
    assert "not responding" in capsys.readouterr().err
