import json
import logging
from datetime import datetime
from pathlib import Path

from .inputs import check_input
from .prompts import AGENT_PROMPT
from .tools import execute, tool_schemas

log = logging.getLogger("defensecoach.agent")

MAX_STEPS = 8


class Agent:
    def __init__(self, client, repo, max_steps=MAX_STEPS, log_file="logs/tool_calls.jsonl"):
        self.client = client
        self.repo = repo
        self.max_steps = max_steps
        self.log_file = Path(log_file) if log_file else None
        self.tools = tool_schemas()
        self.messages = [{"role": "system", "content": AGENT_PROMPT}]
        self.used_tools = []

    def ask(self, user_text):
        user_text = check_input(user_text)
        self.messages.append({"role": "user", "content": user_text})

        for step in range(1, self.max_steps + 1):
            response = self.client.complete(self.messages, tools=self.tools)

            if not response.tool_calls:
                self.messages.append({"role": "assistant", "content": response.text})
                return response.text

            self.messages.append(assistant_message(response))
            for call in response.tool_calls:
                result = execute(self.repo, call.name, call.arguments)
                self.used_tools.append(call.name)
                self.write_log(step, call, result)
                self.messages.append({"role": "tool", "tool_call_id": call.id,
                                      "content": json.dumps(result, ensure_ascii=False)})

        stop_text = (f"I stopped after {self.max_steps} steps without a final answer. "
                     "Try a more specific request.")
        log.warning("step limit reached")
        self.messages.append({"role": "assistant", "content": stop_text})
        return stop_text

    def write_log(self, step, call, result):
        log.info("step %d: %s %s -> ok=%s", step, call.name, call.arguments, result["ok"])
        if self.log_file is None:
            return
        entry = {"time": datetime.now().isoformat(timespec="seconds"), "step": step,
                 "tool": call.name, "args": call.arguments, "ok": result["ok"],
                 "error": result.get("error")}
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def assistant_message(response):
    calls = []
    for call in response.tool_calls:
        calls.append({"id": call.id, "type": "function",
                      "function": {"name": call.name, "arguments": json.dumps(call.arguments)}})
    return {"role": "assistant", "content": response.text, "tool_calls": calls}
