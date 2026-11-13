# Project Proposal — Semester Week 10

## Project Title

**DefenseCoach** — an AI agent that prepares a student for a technical project defense by examining them on their own code repository.

## Problem Description

As a 4th-year student I defend a project almost every week (AI homework, WebMobSec, game development, internship report, and this project itself). Every defense has the same format: the instructor opens my repository and asks *"What does this function do?"*, *"What happens when the API fails?"*, *"How does the agent know when to stop?"*.

Preparing for this alone is hard:

- I re-read my own code but cannot tell which parts I actually understand and which I only *think* I understand.
- Code written with AI assistants is especially risky: it works, but I may not be able to explain it, and the course rules state that code generation alone is not evidence of mastery.
- A friend or instructor who would quiz me is not always available.

This task cannot be solved with a fixed script. A script can list files or run tests, but it cannot read a free-form explanation like *"it just retries if the API fails"*, check it against the real code, decide whether it is correct, partially correct or wrong, and choose what to ask next. That judgment is the job of the LLM; the tools give it access to the facts in the repository.

## Target Users

- Primary: me — a student preparing for weekly defenses of my own course projects.
- Secondary: any student who must explain a code repository to an instructor, interviewer or team lead (e.g., before a job interview where the interviewer asks about a portfolio project).

## Selected Difficulty

C — tool-using agent. The design leaves room to extend toward A (multi-session planning, guardrails, execution limits) if the C-level scope is finished early; any such change will be documented in the weekly reports.

## Expected Functionality

1. **Repository-grounded questions.** The user points the agent at a local repository and (optionally) a focus area. The agent explores the code through tools and asks defense-style questions about real functions, files and decisions.
2. **Answer evaluation.** The user answers in free text. The agent checks the answer against the actual code and returns a structured verdict: `correct` / `partial` / `incorrect`, a short justification with the file and line range it relied on, and what was missing.
3. **Adaptive follow-up.** Depending on the verdict, the agent digs deeper, gives a hint (without revealing the full answer), or moves to another topic.
4. **Claim checking.** If the user states something verifiable (e.g., "all tests pass"), the agent can run the project's configured test command and confront the claim with the result.
5. **Weak-topic memory.** Results are saved per repository, so the next session starts with the topics where the user was weakest.
6. **Session report.** At the end the agent produces a summary: what the user explained well, what to review, and which files to re-read.
7. **Requests without tools.** General questions ("What is tool calling?") are answered directly without touching the repository.

## Proposed Functions

Implementation language: Python 3.11+.

```python
def list_files(subdir: str = ".", pattern: str = "*") -> list[str]:
    """List files in the target repository (relative paths, ignores .git, .env, venv, node_modules)."""

def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> dict:
    """Return {path, start_line, end_line, text}; max 300 lines per call."""

def search_code(query: str, max_results: int = 20) -> list[dict]:
    """Plain-text search across the repository; returns [{path, line, snippet}]."""

def run_tests() -> dict:
    """Run the test command configured for this repository; returns {passed, failed, exit_code, output_tail}."""

def get_progress() -> dict:
    """Return saved results for this repository: {topic: {attempts, last_verdict, notes}}."""

def save_progress(topic: str, verdict: str, note: str) -> dict:
    """Record the verdict for a topic; verdict must be correct | partial | incorrect."""

def evaluate_answer(question: str, answer: str, evidence: list[dict]) -> Verdict:
    """LLM call with structured output; validated against the Verdict schema (not a tool)."""

def call_llm(messages: list, tools: list | None = None) -> LLMResponse:
    """Single wrapper around the model provider (OpenAI / Gemini / Groq / mock) with timeout and retries."""
```

| Function | Purpose | Input | Output | Dependencies |
|---|---|---|---|---|
| `list_files` | See the repository structure | sub-directory, glob pattern | list of relative paths | `pathlib` |
| `read_file` | Read the code a question is about | path, line range | text with line numbers | `pathlib` |
| `search_code` | Find where something is implemented | text query | matches with path and line | `pathlib`, `re` |
| `run_tests` | Verify the user's claims about tests | none (command from config) | pass/fail counts, output tail | `subprocess` with timeout |
| `get_progress` | Load weak topics from past sessions | none | JSON progress | `json` file storage |
| `save_progress` | Store the result of a question | topic, verdict, note | updated progress entry | `json` file storage |
| `evaluate_answer` | Judge a free-text answer | question, answer, code evidence | `Verdict` object | `call_llm`, `pydantic` |
| `call_llm` | Talk to the model | messages, tool schemas | text or tool calls | provider SDK, `.env` |

All file tools are restricted to the target repository directory: absolute paths, `..` and secret files (`.env`, keys) are rejected before execution.

## Proposed Agent Tools

The following functions are registered as LLM-callable tools; the model decides when and whether to call them:

- **`list_files`** — the agent needs an overview of the project to choose which parts to ask about.
- **`read_file`** — questions and verdicts must be based on the real code, not on guesses; the agent reads the relevant lines before asking and before grading.
- **`search_code`** — when the user mentions a function or concept ("the retry logic"), the agent must find where (or whether) it exists.
- **`run_tests`** — the only way to check claims about test results; it runs one fixed command from the configuration, never a command written by the model.
- **`get_progress`** — lets the agent decide where to start a new session.
- **`save_progress`** — lets the agent record what the user still needs to learn.

`evaluate_answer` and `call_llm` are internal functions, not tools. Hard-coded routing is not used: there is no keyword matching that decides which tool runs.

## Model Selection

- **Main model:** OpenAI `gpt-5-mini` through the OpenAI API (paid, a few cents per practice session; I already have API credit). It supports function calling and structured JSON output. `gpt-4o-mini` is the cheaper alternative if spending grows.
- **Free alternatives:** Google Gemini Flash (Google AI Studio free tier) and open models on Groq. Both expose OpenAI-compatible APIs with tool calling, so switching is a change in `.env`.
- **Tests:** a mock client that returns scripted tool calls and responses, so the test suite does not need an API key or network access and can simulate API failures.
- All providers sit behind one `call_llm` wrapper; the provider is selected in `.env`. API keys are never committed (`.env` is in `.gitignore`, `.env.example` is provided). A monthly spending limit is set in the OpenAI dashboard.

## Architecture

```
User (CLI)
   │  "Quiz me on ./css4007-hw4, focus on error handling"
   ▼
Agent loop  ──────────────►  call_llm (OpenAI / Gemini / Groq / Mock)
   │   ▲                          │
   │   │ tool results             │ tool call(s) or text
   │   │                          ▼
   │   └──────  Tool executor ── argument validation (pydantic)
   │              │                + path sandbox + limits
   │              ├── list_files / read_file / search_code ──► target repository (read-only)
   │              ├── run_tests ──────────────────────────────► configured test command (timeout)
   │              └── get_progress / save_progress ───────────► progress.json
   │
   ├── evaluate_answer ──► structured Verdict (validated, retried on invalid JSON)
   │
   └── logs/  — every tool call: name, arguments, duration, result summary or error
```

Flow of one question:
1. The LLM decides which files to inspect and calls the file tools.
2. It asks the user a question grounded in that code.
3. The user answers; `evaluate_answer` returns a validated verdict citing file/line evidence.
4. The LLM chooses the next step (follow-up, hint, new topic) and calls `save_progress`.
5. The loop stops when the user ends the session or a question limit is reached; a session report is printed.

## Example Requests

1. **Start a session:** "Quiz me on my HW4 repository, 5 questions, focus on error handling."
   → `list_files`, `search_code("except")`, `read_file(...)`, then a question such as "What happens in `call_llm` if the provider times out?"
2. **Answer evaluation:** user answers "It retries three times and then shows an error."
   → the agent reads the function, sees there is no retry, returns `incorrect` with the line range, and asks a narrower follow-up.
3. **Claim check:** "All my tests pass, let's skip testing questions."
   → `run_tests`; if two tests fail, the agent says so and asks about one of the failing tests.
4. **Next session:** "Where am I weakest before Friday's defense?"
   → `get_progress`, then starts with the topics marked `incorrect`.
5. **No tools needed:** "What is the difference between a tool and a function?"
   → answered directly, no tool calls in the log.
6. **Missing information:** "Ask me about the database layer." (the repository has none)
   → `search_code` finds nothing; the agent says the project has no database layer instead of inventing questions.

## Evaluation Plan

**Automated tests (pytest, at least 8, mock LLM — no API key needed):**

1. The LLM's tool call for `read_file` is executed and its result is passed back to the model.
2. A request that needs no tools produces an answer with zero tool calls.
3. Path traversal (`../../.env`, absolute paths) is rejected by the sandbox.
4. Invalid tool arguments (wrong type, negative line numbers, unknown verdict) return a validation error to the model instead of crashing.
5. A non-existent file returns a clear "not found" tool error, and the final answer does not invent its content.
6. Invalid JSON from `evaluate_answer` triggers a retry; after repeated failure a readable error is shown.
7. Simulated API failure / timeout in `call_llm` is handled without a traceback.
8. `run_tests` respects the timeout and never executes a model-supplied command.
9. `save_progress` / `get_progress` persist results between sessions.
10. Tool execution logs contain name, arguments and result summary, and never contain API keys.

**Quality evaluation (recorded in `reports/week-16.md`):**

- A fixed set of ~20 question/answer pairs about my previous homework repositories, labelled by me as correct / partial / incorrect. I will measure how often the agent's verdict matches my label and whether its cited lines are actually relevant.
- Tool selection check: for each scripted request, record which tools were called and whether they were appropriate.
- Real use: I will use the agent before my own defenses during the semester and record what it caught.

## Weekly Milestones

| Week | Dates | Plan |
|---|---|---|
| 10 | 02–08 Nov | Fork, choose topic and level, write this proposal, set up the Python project skeleton and `.env.example`. |
| 11 | 09–15 Nov | `call_llm` wrapper for OpenAI/Gemini/Groq, first working request, mock client, basic README with setup instructions. |
| 12 | 16–22 Nov | File tools (`list_files`, `read_file`, `search_code`) with path sandbox; `Verdict` schema and `evaluate_answer` with validation and retry; first tests. |
| 13 | 23–29 Nov | Register tools with the LLM, agent loop with real tool selection, tool execution logs; `run_tests` with timeout. |
| 14 | 30 Nov–06 Dec | Complete session workflow: adaptive follow-ups, hints, `get_progress` / `save_progress`, session report; tool error handling. |
| 15 | 07–13 Dec | Reliability: API failures, invalid output, missing information, prompt-injection text inside repository files; expand tests to 10+. |
| 16 | 14–20 Dec | Run the evaluation set, record results and failures, improve prompts and validation, update documentation. |
| 17 | 21–22 Dec | Final README, final report, AI-assistant usage statement, final commit hash, demonstration and defense. |
