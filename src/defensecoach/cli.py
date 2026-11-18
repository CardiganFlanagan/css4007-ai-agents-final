import argparse
import logging
import sys

from .config import ConfigError, load_settings
from .llm_client import LLMError, make_client
from .prompts import SYSTEM_PROMPT

MAX_INPUT_CHARS = 4000


class InputError(ValueError):
    pass


def check_input(text):
    text = (text or "").strip()
    if not text:
        raise InputError("Empty message. Type a question or an answer.")
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(f"Message is too long ({len(text)} chars, max {MAX_INPUT_CHARS}).")
    return text


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


def chat(client, settings):
    history = []
    print(f"DefenseCoach ({settings.provider}: {settings.model}). Type 'exit' to quit.")
    while True:
        try:
            line = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.strip().lower() in ("exit", "quit"):
            return 0
        try:
            print("coach>", ask_once(client, line, history))
        except (InputError, LLMError) as e:
            print(f"Error: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="defensecoach", description="Defense trainer agent")
    parser.add_argument("message", nargs="?", help="one message to send")
    parser.add_argument("--chat", action="store_true", help="conversation mode")
    parser.add_argument("-v", "--verbose", action="store_true", help="show logs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
        client = make_client(settings)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if args.chat:
        return chat(client, settings)
    if not args.message:
        parser.print_help()
        return 1
    try:
        print(ask_once(client, args.message))
        return 0
    except (InputError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
