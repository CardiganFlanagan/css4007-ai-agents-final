# Semester Week 10 Progress Report

## Completed Work

- Forked the instructor repository and read the project rules and the C-level requirements.
- Compared several topic ideas (a recipe-designer agent for my game, a study planner, an internship assistant) and chose DefenseCoach, an agent that prepares me for project defenses using my own repositories. I chose it because I defend projects almost every week and the task needs the model's judgment (evaluating free-text answers), not only tool calls.
- Wrote `reports/proposal.md`: problem, users, level C, functions and tools, model choice, architecture, example requests, evaluation plan and milestones. `npm run proposal` passes.

## Important Commits

- Commit hash: <proposal commit hash>
- Description: Add project proposal: DefenseCoach (C level)
- Link: https://github.com/<username>/css4007-ai-agents-final/commit/<proposal commit hash>

## Current Functionality

No application code yet. The design, the tool list and the plan are fixed in the proposal.

## Problems Encountered

My first idea (an agent that designs recipes for my game) was not meaningful enough for my everyday life, and the game itself is not ready. The task also had to need real agent decisions, not only a fixed sequence of tool calls.

## Solutions

I switched to a task I actually face every week (defending code). In this task the LLM must decide what to read, judge my answer against the real code and choose the next question, which a script cannot do.

## What I Learned

- How to tell a real agent task from a pipeline: if a fixed `if/else` script can solve it, it does not need an agent.
- Free-tier options for LLM APIs (Gemini, Groq) and that a paid chat subscription does not include API access.

## Next Week

Week 11: set up the Python project, implement the LLM wrapper for Gemini/Groq with error handling, make the first working request and add the first tests.
