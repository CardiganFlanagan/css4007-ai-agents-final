import argparse
import logging
import sys

from .agent import Agent
from .config import ConfigError, load_settings
from .inputs import InputError, check_input
from .llm_client import LLMError, make_client
from .prompts import SYSTEM_PROMPT
from .tools import Repo, ToolError



def ask_once(client, user_text, history=None):
    user_text = check_input(user_text)
    if history is None:
        history = []
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_text}]

    response = client.complete(messages)
    if not response.text:
        raise LLMError("The model did not return any text.")

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": response.text})
    return response.text


def chat(send, title):
    print(title)
    print("Type 'exit' to quit.")
    while True:
        try:
            line = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.strip().lower() in ("exit", "quit"):
            return 0
        try:
            print("coach>", send(line))
        except (InputError, LLMError) as e:
            print(f"Error: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="defensecoach", description="Defense trainer agent")
    parser.add_argument("message", nargs="?", help="one message to send")
    parser.add_argument("--repo", help="path to the project you want to be examined on")
    parser.add_argument("--chat", action="store_true", help="conversation mode")
    parser.add_argument("-v", "--verbose", action="store_true", help="show logs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
        client = make_client(settings)
        repo = Repo(args.repo) if args.repo else None
    except (ConfigError, ToolError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if repo:
        agent = Agent(client, repo)
        send = agent.ask
        title = f"DefenseCoach on {repo.root.name} ({settings.provider}: {settings.model})"
    else:
        history = []
        send = lambda text: ask_once(client, text, history)
        title = f"DefenseCoach ({settings.provider}: {settings.model})"

    if args.chat:
        return chat(send, title)
    if not args.message:
        parser.print_help()
        return 1
    try:
        print(send(args.message))
        return 0
    except (InputError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
