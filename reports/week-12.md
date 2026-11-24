# Semester Week 12 Progress Report

## Completed Work

- Added the repository tools in `tools.py`: `list_files`, `read_file` (with line numbers, max 300 lines per call) and `search_code` (case-insensitive text search).
- Built a path sandbox: every path must be relative to the repository; `..`, absolute paths and symlinks that lead outside are rejected. `.env`, key files, `.git` and `.venv` are hidden from listing and search and cannot be read.
- Added argument validation with pydantic models for each tool and an `execute(name, arguments)` function that returns `{"ok": false, "error": ...}` instead of crashing. Every tool call is logged with its name, arguments and result.
- Tool JSON schemas are generated from the same pydantic models, so they are ready to be registered with the LLM next week.
- Added answer grading in `evaluation.py`: the `Verdict` schema (`correct` / `partial` / `incorrect`, explanation, missing points, citations, follow-up question) and `evaluate_answer`, which asks the model for JSON, validates it and retries with the error explained (max 3 attempts).
- The grader must cite lines inside the code it was given; a citation to code it did not see is rejected as invented.
- Added JSON mode to the LLM client and a `try_grade` command to grade one answer by hand.
- Simplified the code from week 11: removed extra type machinery and split long functions, so every part is easy to read and explain.
- 28 new tests (46 in total), all without an API key.

## Important Commits

- Commit hash: 3fa0c60
- Description: Repository tools with path sandbox and structured answer grading
- Link: https://github.com/CardiganFlanagan/css4007-ai-agents-final/commit/3fa0c60

## Current Functionality

I can point the program at a repository, read and search its code safely, and grade a free-text answer against a code fragment. Example: for the question "What happens when the provider times out?" and the answer "It retries three times", the grader reads the fragment, returns `incorrect` or `partial` with the exact lines, explains what is missing and suggests a follow-up question. The tools are not yet called by the model itself. That is the week 13 agent loop.

## Problems Encountered

- The agent will read the user's repository, so a careless path like `../../.env` could leak secrets.
- The model does not always return clean JSON: sometimes it wraps it in a code fence, uses a verdict value that is not allowed, or leaves out fields.
- The grader could "prove" its verdict by citing code it never received.

## Solutions

- All paths go through one `resolve()` function that resolves the real path and checks that it stays inside the repository; secret files are blocked by name.
- JSON mode in the API, extraction of JSON from code fences, strict pydantic validation and a retry that tells the model exactly what was wrong.
- A citation check: every cited range must lie inside the fragments that were sent to the model.

## What I Learned

- Path traversal and why checking the string is not enough: the path has to be resolved first (`src/../../x`, symlinks).
- How to get reliable structured output from an LLM: schema, validation, feedback, limited retries.
- Using one pydantic model for both argument validation and the tool schema the model sees.

## Next Week

Week 13, tool integration: register the tools with the LLM, write the agent loop where the model decides which tools to call, pass tool results and errors back to the model, add `run_tests`, `get_progress` and `save_progress`, a step limit, and tests that check tool selection.
