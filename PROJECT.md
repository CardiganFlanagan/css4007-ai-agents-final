# DefenseCoach

An LLM agent that prepares a student for the technical defense of their own project:
it reads the student's repository, asks defense-style questions, checks answers against
the real code, and decides what to ask next. Proposal: [reports/proposal.md](reports/proposal.md).

**Status (week 11):** LLM integration and first working request. Tools and the agent loop come in weeks 12–13.

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
# one request
PYTHONPATH=src python -m defensecoach "Ask me one defense question about API error handling"

# conversation (type 'exit' to quit), -v shows LLM call logs
PYTHONPATH=src python -m defensecoach --chat -v
```

On Windows PowerShell set the path first: `$env:PYTHONPATH="src"`.

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
| `src/defensecoach/prompts.py` | System prompt of the examiner |
| `src/defensecoach/cli.py` | Command line: input validation, single request and chat mode |
| `tests/test_llm_client.py` | Week 11 tests |

## Error handling

| Situation | Behaviour |
|---|---|
| No key / unknown provider | Clear configuration error, exit code 2 |
| Timeout, connection error, rate limit, 5xx | Retried with backoff (1s, 2s), then "service is not responding" |
| Wrong key, unknown model, bad request | Not retried (it would not help), clear message |
| Empty or too-long input | Rejected before calling the model |
| Empty model output or broken tool-call JSON | `LLMError` with an explanation |

## AI assistance

Claude (Anthropic) was used to help draft the proposal and the initial code structure.
All code was reviewed, run and tested by me; details per week are in `reports/`.
