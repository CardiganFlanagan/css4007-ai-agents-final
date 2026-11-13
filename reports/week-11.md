# Semester Week 11 Progress Report

## Completed Work

- Set up the Python project: `src/defensecoach` package, `requirements.txt`, `pytest.ini`, `.env.example`.
- Implemented the LLM wrapper (`llm_client.py`): one `complete(messages, tools)` interface for OpenAI, Gemini and Groq through the OpenAI-compatible chat API, plus a `MockClient` for tests and offline demos.
- Added error handling: transient errors (timeout, connection, rate limit, 5xx) are retried with exponential backoff; permanent errors (bad key, unknown model) fail immediately with a clear message.
- Response parsing already supports tool calls (needed in week 13) and rejects empty output and invalid tool-argument JSON.
- First working request: `python -m defensecoach "..."` and a multi-turn `--chat` mode with the examiner system prompt.
- Added `PROJECT.md` with setup, run and test instructions.
- 18 automated tests (pytest), all passing without an API key.

## Important Commits

- Commit hash: <hash 1>
- Description: Project skeleton, configuration loading and LLM wrapper for OpenAI/Gemini/Groq
- Link: https://github.com/<username>/css4007-ai-agents-final/commit/<hash 1>

- Commit hash: <hash 2>
- Description: Mock client and tests for retries, failures and response parsing
- Link: https://github.com/<username>/css4007-ai-agents-final/commit/<hash 2>

- Commit hash: <hash 3>
- Description: CLI with first working request, chat mode and documentation
- Link: https://github.com/<username>/css4007-ai-agents-final/commit/<hash 3>

## Current Functionality

The application sends a question to OpenAI `gpt-5-mini` (or Gemini / Groq / mock) with the DefenseCoach system prompt and prints the examiner's reply. In chat mode it keeps the conversation history, so it can ask a question, receive my answer and react to it. It does not read repositories yet. That is the next step.

## Problems Encountered

- OpenAI, Gemini and Groq have different native SDKs, and I did not want several code paths.
- The OpenAI SDK has its own hidden retries, which made failure behaviour hard to test and explain.
- Tests must not depend on an API key, internet access or free-tier rate limits.

## Solutions

- Gemini and Groq offer OpenAI-compatible endpoints, so one client with a different `base_url` covers all three providers.
- I disabled the SDK's built-in retries (`max_retries=0`) and wrote my own retry loop, so I control which errors are retried and the tests can check it.
- The real client accepts an injected SDK object. Tests pass a fake SDK that returns or raises scripted results, and the sleep function is injected so tests run instantly.

## What I Learned

- The difference between transient errors (worth retrying) and permanent errors (retrying only wastes quota).
- Exponential backoff and why the number of retries must be limited.
- How the chat-completions format represents tool calls (`tool_calls` with JSON-string arguments) and why those arguments must be validated.
- Dependency injection as a way to test code that talks to an external API.

## Next Week

Week 12, core functionality: the file tools (`list_files`, `read_file`, `search_code`) with a path sandbox, the `Verdict` schema with `evaluate_answer` (structured output, validation and retry on invalid JSON), and tests for path traversal and invalid arguments.
