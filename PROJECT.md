# DefenseCoach

An LLM agent that prepares a student for the technical defense of their own project:
it reads the student's repository, asks defense-style questions, checks answers against
the real code, and decides what to ask next. Proposal: [reports/proposal.md](reports/proposal.md).

**Status (week 13):** working agent. The model decides by itself which tools to call (read code, search, run tests, load and save progress), gets the results back and continues until it can answer. Next: the full practice session with grading and a session report (week 14).

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then put your key into .env
```

Default provider is OpenAI (`LLM_PROVIDER=openai`, `LLM_MODEL=gpt-5-mini`): put your OpenAI API key
into `LLM_API_KEY`. Alternatives: `gemini` (free tier, key from Google AI Studio) or `groq`.
`LLM_PROVIDER=mock` runs without any key or internet. Set a monthly spending limit in the
OpenAI dashboard; tests never call the real API.

## Run

```bash
# practice session on one of your projects (the agent reads its code through tools)
PYTHONPATH=src python -m defensecoach --repo ../css4007-hw4 --chat -v

# one request
PYTHONPATH=src python -m defensecoach "Ask me one defense question about API error handling"

# conversation (type 'exit' to quit), -v shows LLM call logs
PYTHONPATH=src python -m defensecoach --chat -v

# grade one answer against a fragment of real code
PYTHONPATH=src python -m defensecoach.try_grade --repo . --file src/defensecoach/llm_client.py --lines 55-85 \
    --question "What happens when the provider times out?" --answer "It retries three times and then shows an error"
```

On Windows PowerShell set the path first: `$env:PYTHONPATH="src"`.

`-v` prints every tool call. All tool calls are also written to `logs/tool_calls.jsonl`,
and results per project are saved in `progress/<project>.json` (both folders are ignored by git).

By default `run_tests` runs `python -m pytest -q` in the examined project. Another command can be set
in a `defensecoach.json` file in that project, for example:

```json
{"test_command": ["npm", "test"], "test_timeout": 120}
```

The model can only trigger this fixed command; it cannot pass its own command.

## Tests

```bash
python -m pytest -q
```

Tests use a fake SDK and a mock client, so they need no API key.

## Code map

| File | What it does |
|---|---|
| `src/defensecoach/config.py` | Reads `.env`, validates settings, hides the API key in logs |
| `src/defensecoach/llm_client.py` | `call_llm` wrapper: one interface for OpenAI / Gemini / Groq / mock, retries with backoff, error types, response parsing |
| `src/defensecoach/prompts.py` | Examiner and grader prompts |
| `src/defensecoach/agent.py` | Agent loop: sends tool schemas, runs the tools the model asks for, returns results, step limit, tool log |
| `src/defensecoach/tools.py` | `list_files`, `read_file`, `search_code`, `run_tests`, `get_progress`, `save_progress`, path sandbox, argument validation, tool schemas |
| `src/defensecoach/evaluation.py` | `Verdict` schema and `evaluate_answer`: JSON output, validation, citation check, retries |
| `src/defensecoach/try_grade.py` | Command to grade one answer by hand |
| `src/defensecoach/cli.py` | Command line: agent mode with `--repo`, single request and chat mode |
| `src/defensecoach/inputs.py` | User input checks |
| `tests/test_llm_client.py` | LLM client, config and CLI tests |
| `tests/test_tools.py` | Tool and sandbox tests |
| `tests/test_evaluation.py` | Grading tests |
| `tests/test_agent.py` | Agent loop, tool selection, run_tests, progress, CLI agent mode |

## Error handling

| Situation | Behaviour |
|---|---|
| No key / unknown provider | Clear configuration error, exit code 2 |
| Timeout, connection error, rate limit, 5xx | Retried with backoff (1s, 2s), then "service is not responding" |
| Wrong key, unknown model, bad request | Not retried (it would not help), clear message |
| Empty or too-long input | Rejected before calling the model |
| Empty model output or broken tool-call JSON | `LLMError` with an explanation |
| Path outside the repository, `..`, absolute path, symlink out | Rejected by the sandbox |
| `.env`, keys, `.git`, `.venv` | Hidden from listing and search, reading is refused |
| Wrong tool arguments (negative line, wrong type, unknown tool) | Error returned to the model, no crash |
| Missing, binary or huge file | Clear tool error |
| Grader returns broken JSON, wrong verdict value or cites code it was not given | Retried with the error explained, max 3 attempts |
| Model keeps calling tools without answering | Stops after 8 steps with a message |
| Tests hang or the test command is missing | Timeout / clear tool error |
| Wrong `--repo` path | Clear error, exit code 2 |

## AI assistance

Claude (Anthropic) was used to help draft the proposal and the initial code structure.
All code was reviewed, run and tested by me; details per week are in `reports/`.
