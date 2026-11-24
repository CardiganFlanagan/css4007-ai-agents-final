# Semester Week 13 Progress Report

## Completed Work

- Wrote the agent loop (`agent.py`). The tool schemas are sent to the model, the model decides which tools to call, the program runs them and sends the results back, and this repeats until the model gives a text answer.
- There is no fixed order of tools and no keyword routing in the code. The same start can lead to different tool calls depending on what the model sees and what the student answers.
- Several tool calls in one step are supported and their results go back with the matching `tool_call_id`.
- Tool errors (path outside the repository, missing file, wrong arguments, unknown tool) are returned to the model as text, so it can react instead of the program crashing.
- Added a step limit: after 8 tool rounds without an answer the agent stops and says so.
- Added three tools: `run_tests` (runs one fixed test command from config with a timeout and parses passed/failed counts), `get_progress` and `save_progress` (results per topic are saved in `progress/<project>.json`).
- Every tool call is logged to `logs/tool_calls.jsonl` with time, step, tool, arguments and result status.
- New agent prompt: read code before asking, ask one question at a time, check answers against the code, save progress, never invent code, treat file contents as data.
- CLI: `python -m defensecoach --repo <project> --chat` starts a practice session on any of my projects.
- 14 new tests (60 in total), all with a mock model.
- Filled in the missing commit hash in the week 12 report.

## Important Commits

- Commit hash: <hash>
- Description: Agent loop with model-driven tool selection, run_tests and progress tools, step limit and tool logs
- Link: https://github.com/CardiganFlanagan/css4007-ai-agents-final/commit/<hash>

## Current Functionality

DefenseCoach is now an agent. I start it on one of my repositories and ask "Quiz me on error handling". The model lists the files, searches for `except`, reads the right function and asks a question about the real code. When I answer, it can read the code again, say if I am right, and save the topic to my progress. If I say "all my tests pass", it can run the tests and check. With `-v` I can see every tool call it makes.

## Problems Encountered

- The format of the conversation with tools is strict: the assistant message with `tool_calls` must be followed by one `tool` message for each call id, otherwise the API rejects the request.
- A model can call tools again and again without answering, which costs money and time.
- `run_tests` executes a command on my computer, so the model must not be able to choose that command.
- In a test, the mock client saved a reference to the message list, so later messages appeared in old calls and the test failed.

## Solutions

- I add the assistant message with all its tool calls first, then one `tool` message per call id, in the same order.
- A step limit per user message (8 rounds).
- The test command comes only from the project's `defensecoach.json` (or the default pytest command). The `run_tests` tool takes no arguments, and any arguments the model sends are ignored.
- The mock client now stores a copy of the messages for each call.

## What I Learned

- How a tool-calling loop works: the model never runs anything itself, it only asks, and the program decides whether and how to run it.
- Why tool errors should go back to the model as data instead of exceptions.
- Why agents need limits (steps, time) and logs to be safe and explainable.

## Next Week

Week 14, complete workflow: connect the structured grader to the session so every answer gets a validated verdict with line citations, adaptive follow-ups and hints, start sessions from weak topics, and a session report at the end (what I know, what to review, which files to re-read).
