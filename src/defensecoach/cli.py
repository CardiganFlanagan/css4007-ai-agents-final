from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, load_settings
from .llm_client import LLMClient, LLMError, make_client
from .prompts import SYSTEM_PROMPT

MAX_INPUT_CHARS = 4000


class InputError(ValueError):
    pass


def validate_user_input(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise InputError("Empty message. Type a question or an answer.")
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(f"Message is too long ({len(text)} chars, max {MAX_INPUT_CHARS}).")
    return text


def ask_once(client: LLMClient, user_text: str, history: list[dict] | None = None) -> str:
    user_text = validate_user_input(user_text)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []),
                {"role": "user", "content": user_text}]
    response = client.complete(messages)
    if not response.text:
        raise LLMError("The model did not return any text.")
    if history is not None:
        history += [{"role": "user", "content": user_text},
                    {"role": "assistant", "content": response.text}]
    return response.text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="defensecoach", description="Defense trainer agent (week 11 prototype)")
    parser.add_argument("message", nargs="?", help="one message to send")
    parser.add_argument("--chat", action="store_true", help="interactive multi-turn mode")
    parser.add_argument("-v", "--verbose", action="store_true", help="show LLM call logs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = load_settings()
        client = make_client(settings)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if not args.chat:
        if not args.message:
            parser.print_help()
            return 1
        try:
            print(ask_once(client, args.message))
            return 0
        except (InputError, LLMError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    history: list[dict] = []
    print(f"DefenseCoach ({settings.provider}:{settings.model}). Type 'exit' to quit.")
    while True:
        try:
            line = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.strip().lower() in {"exit", "quit"}:
            return 0
        try:
            print("coach>", ask_once(client, line, history))
        except (InputError, LLMError) as exc:
            print(f"Error: {exc}")
