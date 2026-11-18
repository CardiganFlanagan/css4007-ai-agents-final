import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .prompts import EVALUATOR_PROMPT
from .tools import short_error

log = logging.getLogger("defensecoach.eval")

MAX_ANSWER_CHARS = 3000
MAX_ATTEMPTS = 3


class EvaluationError(Exception):
    pass


class Citation(BaseModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class Verdict(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"]
    explanation: str = Field(min_length=10)
    missing_points: list[str] = []
    citations: list[Citation] = Field(min_length=1)
    follow_up: str = Field(min_length=5)


class Evidence(BaseModel):
    path: str
    start_line: int
    end_line: int
    text: str


def cut_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        return text
    return text[start:end + 1]


def check_citations(verdict, evidence):
    for c in verdict.citations:
        found = False
        for e in evidence:
            if e.path == c.path and e.start_line <= c.start_line <= c.end_line <= e.end_line:
                found = True
        if not found:
            raise ValueError(f"citation {c.path}:{c.start_line}-{c.end_line} is not inside the provided code")


def build_prompt(question, answer, evidence):
    code = ""
    for e in evidence:
        code += f"File {e.path}, lines {e.start_line}-{e.end_line}:\n{e.text}\n\n"
    return f"Code:\n{code}Question: {question}\n\nStudent answer: {answer}"


def evaluate_answer(client, question, answer, evidence):
    answer = (answer or "").strip()
    if not answer:
        raise EvaluationError("The answer is empty.")
    if len(answer) > MAX_ANSWER_CHARS:
        raise EvaluationError(f"The answer is too long (max {MAX_ANSWER_CHARS} characters).")
    if not evidence:
        raise EvaluationError("No code was provided to check the answer against.")
    evidence = [e if isinstance(e, Evidence) else Evidence(**e) for e in evidence]

    messages = [
        {"role": "system", "content": EVALUATOR_PROMPT},
        {"role": "user", "content": build_prompt(question, answer, evidence)},
    ]
    problem = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = client.complete(messages, json_mode=True).text or ""
        try:
            verdict = Verdict.model_validate_json(cut_json(raw))
            check_citations(verdict, evidence)
            log.info("verdict=%s attempt=%d", verdict.verdict, attempt)
            return verdict
        except ValidationError as e:
            problem = short_error(e)
        except ValueError as e:
            problem = str(e)
        log.warning("bad verdict on attempt %d: %s", attempt, problem)
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"Your JSON was rejected: {problem}. "
                                                    "Return only a corrected JSON object."})
    raise EvaluationError(f"The model did not return a valid verdict after {MAX_ATTEMPTS} attempts ({problem}).")
