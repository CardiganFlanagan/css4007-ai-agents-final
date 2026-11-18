import json

import pytest

from defensecoach.evaluation import EvaluationError, evaluate_answer
from defensecoach.llm_client import LLMResponse, MockClient

EVIDENCE = [{"path": "src/client.py", "start_line": 1, "end_line": 5,
             "text": "1: def call_llm():\n2:     try:\n3:         return send()\n"
                     "4:     except TimeoutError:\n5:         raise"}]
QUESTION = "What happens in call_llm when the provider times out?"


def verdict_json(**over):
    data = {"verdict": "incorrect",
            "explanation": "Line 5 re-raises the timeout, there is no retry.",
            "missing_points": ["no retry, the error goes to the caller"],
            "citations": [{"path": "src/client.py", "start_line": 4, "end_line": 5}],
            "follow_up": "Who catches the error after line 5?"}
    data.update(over)
    return json.dumps(data)


def reply(text):
    return LLMResponse(text=text)


def test_valid_verdict_is_parsed_and_json_mode_is_requested():
    mock = MockClient([reply(verdict_json())])
    result = evaluate_answer(mock, QUESTION, "It retries three times", EVIDENCE)
    assert result.verdict == "incorrect"
    assert result.citations[0].start_line == 4
    assert mock.calls[0]["json_mode"] is True
    prompt = mock.calls[0]["messages"][1]["content"]
    assert "4:     except TimeoutError:" in prompt and "It retries three times" in prompt


def test_json_inside_code_fence_is_accepted():
    mock = MockClient([reply("Here you go:\n```json\n" + verdict_json(verdict="partial") + "\n```")])
    assert evaluate_answer(mock, QUESTION, "It raises", EVIDENCE).verdict == "partial"


def test_broken_json_is_retried_with_feedback():
    mock = MockClient([reply("{not json"), reply(verdict_json())])
    assert evaluate_answer(mock, QUESTION, "It retries", EVIDENCE).verdict == "incorrect"
    assert len(mock.calls) == 2
    assert "rejected" in mock.calls[1]["messages"][-1]["content"]


def test_unknown_verdict_value_is_retried():
    mock = MockClient([reply(verdict_json(verdict="maybe")), reply(verdict_json(verdict="correct"))])
    assert evaluate_answer(mock, QUESTION, "It re-raises", EVIDENCE).verdict == "correct"
    assert "verdict" in mock.calls[1]["messages"][-1]["content"]


def test_citation_outside_given_code_is_rejected():
    invented = verdict_json(citations=[{"path": "src/retry.py", "start_line": 1, "end_line": 9}])
    mock = MockClient([reply(invented), reply(verdict_json())])
    evaluate_answer(mock, QUESTION, "It retries", EVIDENCE)
    assert "not inside the provided code" in mock.calls[1]["messages"][-1]["content"]


def test_gives_up_after_three_bad_attempts():
    mock = MockClient([reply("nope"), reply("{}"), reply('{"verdict": "correct"}')])
    with pytest.raises(EvaluationError, match="after 3 attempts"):
        evaluate_answer(mock, QUESTION, "It retries", EVIDENCE)
    assert len(mock.calls) == 3


@pytest.mark.parametrize("answer,evidence,message", [
    ("   ", EVIDENCE, "empty"),
    ("x" * 3001, EVIDENCE, "too long"),
    ("It retries", [], "No code"),
])
def test_bad_input_is_rejected_before_calling_the_model(answer, evidence, message):
    mock = MockClient()
    with pytest.raises(EvaluationError, match=message):
        evaluate_answer(mock, QUESTION, answer, evidence)
    assert mock.calls == []
