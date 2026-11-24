import json
import sys

import pytest

from defensecoach.agent import Agent
from defensecoach.cli import main
from defensecoach.inputs import InputError
from defensecoach.llm_client import LLMResponse, LLMUnavailableError, MockClient, ToolCall
from defensecoach.tools import Repo, execute


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "hw4"
    (root / "src").mkdir(parents=True)
    (root / "src" / "llm.py").write_text(
        "def call_llm(prompt):\n    try:\n        return send(prompt)\n    except TimeoutError:\n        raise\n",
        encoding="utf-8")
    (root / ".env").write_text("LLM_API_KEY=sk-secret\n", encoding="utf-8")
    return Repo(root, progress_dir=tmp_path / "progress")


def tool(name, call_id="c1", **args):
    return LLMResponse(None, [ToolCall(call_id, name, args)])


def text(t):
    return LLMResponse(t)


def make_agent(script, repo, tmp_path, max_steps=8):
    mock = MockClient(script)
    return Agent(mock, repo, max_steps=max_steps, log_file=tmp_path / "logs" / "calls.jsonl"), mock


def tool_messages(mock, call_number):
    return [m for m in mock.calls[call_number]["messages"] if m["role"] == "tool"]


def test_model_chooses_tool_and_gets_result_back(repo, tmp_path):
    agent, mock = make_agent([tool("read_file", path="src/llm.py", start_line=1, end_line=5),
                              text("What happens on line 5 when the provider times out?")], repo, tmp_path)
    answer = agent.ask("Quiz me on error handling")

    assert answer == "What happens on line 5 when the provider times out?"
    assert agent.used_tools == ["read_file"]
    result = json.loads(tool_messages(mock, 1)[0]["content"])
    assert result["ok"] and "5:         raise" in result["result"]["text"]
    assert tool_messages(mock, 1)[0]["tool_call_id"] == "c1"
    assert mock.calls[0]["tools"] and len(mock.calls[0]["tools"]) == 6


def test_general_question_needs_no_tools(repo, tmp_path):
    agent, mock = make_agent([text("A tool is a function the model can ask the program to run.")], repo, tmp_path)
    agent.ask("What is a tool in an LLM agent?")
    assert agent.used_tools == []
    assert len(mock.calls) == 1


def test_several_tool_calls_in_one_step_run_in_order(repo, tmp_path):
    two_calls = LLMResponse(None, [ToolCall("a", "list_files", {}), ToolCall("b", "search_code", {"query": "timeout"})])
    agent, mock = make_agent([two_calls, text("ok")], repo, tmp_path)
    agent.ask("Look around")
    assert agent.used_tools == ["list_files", "search_code"]
    assert [m["tool_call_id"] for m in tool_messages(mock, 1)] == ["a", "b"]
    assistant = [m for m in mock.calls[1]["messages"] if m.get("tool_calls")][0]
    assert assistant["tool_calls"][1]["function"]["name"] == "search_code"


def test_tool_error_goes_back_to_model_instead_of_crashing(repo, tmp_path):
    agent, mock = make_agent([tool("read_file", path="../../.env"),
                              tool("read_file", "c2", path="src/missing.py"),
                              text("That file does not exist in your project.")], repo, tmp_path)
    assert agent.ask("Read the env file") == "That file does not exist in your project."
    first, second = [json.loads(m["content"]) for m in tool_messages(mock, 2)]
    assert first == {"ok": False, "error": "Path is outside the repository."}
    assert second["error"] == "File not found: src/missing.py"
    assert "sk-secret" not in json.dumps(mock.calls[-1]["messages"])


def test_invalid_arguments_and_unknown_tool_are_reported(repo, tmp_path):
    agent, mock = make_agent([tool("read_file", start_line="abc"), tool("rm_rf", "c2"), text("done")],
                             repo, tmp_path)
    agent.ask("go")
    errors = [json.loads(m["content"])["error"] for m in tool_messages(mock, 2)]
    assert errors[0].startswith("Invalid arguments") and errors[1] == "Unknown tool 'rm_rf'."


def test_step_limit_stops_endless_tool_calls(repo, tmp_path):
    loop = [tool("list_files", f"c{i}") for i in range(10)]
    agent, mock = make_agent(loop, repo, tmp_path, max_steps=3)
    answer = agent.ask("Explore forever")
    assert "stopped after 3 steps" in answer
    assert len(mock.calls) == 3


def test_history_is_kept_between_questions(repo, tmp_path):
    agent, mock = make_agent([text("Question 1?"), text("Partially correct.")], repo, tmp_path)
    agent.ask("start")
    agent.ask("my answer")
    contents = [m["content"] for m in mock.calls[1]["messages"][1:]]
    assert contents == ["start", "Question 1?", "my answer"]


def test_empty_input_and_api_failure(repo, tmp_path):
    agent, mock = make_agent([LLMUnavailableError("The model service is not responding right now.")], repo, tmp_path)
    with pytest.raises(InputError):
        agent.ask("   ")
    assert mock.calls == []
    with pytest.raises(LLMUnavailableError):
        agent.ask("hello")


def test_tool_calls_are_logged_without_secrets(repo, tmp_path):
    agent, _ = make_agent([tool("read_file", path=".env"), text("no")], repo, tmp_path)
    agent.ask("show me secrets")
    lines = (tmp_path / "logs" / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert entry["tool"] == "read_file" and entry["ok"] is False and entry["step"] == 1
    assert "sk-secret" not in lines[0]


def write_config(repo, **config):
    (repo.root / "defensecoach.json").write_text(json.dumps(config), encoding="utf-8")
    return Repo(repo.root, progress_dir=repo.progress_file.parent)


def test_run_tests_parses_pytest_summary(repo):
    repo = write_config(repo, test_command=[sys.executable, "-c", "print('== 3 passed, 1 failed in 0.1s ==')"])
    result = execute(repo, "run_tests", {})
    assert result["ok"]
    assert result["result"]["passed"] == 3 and result["result"]["failed"] == 1


def test_run_tests_timeout_and_ignores_model_arguments(repo):
    repo = write_config(repo, test_command=[sys.executable, "-c", "import time; time.sleep(5)"], test_timeout=1)
    result = execute(repo, "run_tests", {"command": "del /s /q C:\\"})
    assert result == {"ok": False, "error": "Tests did not finish in 1 seconds."}


def test_progress_is_saved_and_loaded(repo):
    execute(repo, "save_progress", {"topic": "timeouts", "verdict": "incorrect", "note": "no retry"})
    execute(repo, "save_progress", {"topic": "timeouts", "verdict": "partial"})
    again = Repo(repo.root, progress_dir=repo.progress_file.parent)
    topics = execute(again, "get_progress", {})["result"]["topics"]
    assert topics["timeouts"]["attempts"] == 2 and topics["timeouts"]["last_verdict"] == "partial"
    assert execute(repo, "save_progress", {"topic": "x", "verdict": "great"})["ok"] is False


def test_cli_repo_mode_uses_agent(repo, tmp_path, monkeypatch, capsys):
    mock = MockClient([tool("list_files"), text("Your project has one file. What does call_llm do?")])
    monkeypatch.setattr("defensecoach.cli.make_client", lambda s: mock)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert main(["--repo", str(repo.root), "Quiz me"]) == 0
    assert "What does call_llm do?" in capsys.readouterr().out
    assert mock.calls[0]["tools"]


def test_cli_bad_repo_path(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert main(["--repo", "/no/such/folder", "hi"]) == 2
    assert "Repository folder not found" in capsys.readouterr().err
