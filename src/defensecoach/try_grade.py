import argparse
import json
import logging
import sys

from .config import ConfigError, load_settings
from .evaluation import EvaluationError, Evidence, evaluate_answer
from .llm_client import LLMError, make_client
from .tools import Repo, ToolError, read_file


def main(argv=None):
    parser = argparse.ArgumentParser(prog="try_grade", description="Grade one answer against a piece of code")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--file", required=True)
    parser.add_argument("--lines", default="1-80", help="for example 40-90")
    parser.add_argument("--question", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        start, end = args.lines.split("-")
        start, end = int(start), int(end)
    except ValueError:
        print("Error: --lines must look like 40-90", file=sys.stderr)
        return 1

    try:
        piece = read_file(Repo(args.repo), args.file, start, end)
        client = make_client(load_settings())
        verdict = evaluate_answer(client, args.question, args.answer, [Evidence(**piece)])
    except (ConfigError, ToolError, EvaluationError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(verdict.model_dump(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
