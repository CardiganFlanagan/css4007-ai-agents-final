import fnmatch
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("defensecoach.tools")

HIDDEN_FOLDERS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".idea", ".vscode"}
SECRET_FILES = [".env", ".env.*", "*.pem", "*.key", "id_rsa*", "*.p12", "secrets.*"]
MAX_FILES = 200
MAX_LINES = 300
MAX_FILE_SIZE = 1_000_000
CONFIG_FILE = "defensecoach.json"
DEFAULT_TEST_COMMAND = [sys.executable, "-m", "pytest", "-q"]
DEFAULT_TEST_TIMEOUT = 120


class ToolError(Exception):
    pass


def is_secret(filename):
    if filename == ".env.example":
        return False
    for pattern in SECRET_FILES:
        if fnmatch.fnmatch(filename.lower(), pattern):
            return True
    return False


class Repo:
    def __init__(self, folder, progress_dir="progress"):
        self.root = Path(folder).resolve()
        if not self.root.is_dir():
            raise ToolError(f"Repository folder not found: {folder}")
        self.progress_file = Path(progress_dir) / f"{self.root.name}.json"
        self.test_command = DEFAULT_TEST_COMMAND
        self.test_timeout = DEFAULT_TEST_TIMEOUT
        self.load_config()

    def load_config(self):
        config_path = self.root / CONFIG_FILE
        if not config_path.is_file():
            return
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise ToolError(f"{CONFIG_FILE} is not valid JSON.")
        command = config.get("test_command", self.test_command)
        if not isinstance(command, list) or not all(isinstance(x, str) for x in command) or not command:
            raise ToolError(f"test_command in {CONFIG_FILE} must be a list of strings.")
        self.test_command = command
        self.test_timeout = int(config.get("test_timeout", self.test_timeout))

    def safe_path(self, path):
        path = (path or ".").strip().replace("\\", "/")
        if path.startswith("/") or Path(path).is_absolute() or path[1:2] == ":":
            raise ToolError("Only paths relative to the repository are allowed.")

        full_path = (self.root / path).resolve()
        if full_path != self.root and self.root not in full_path.parents:
            raise ToolError("Path is outside the repository.")

        parts = full_path.relative_to(self.root).parts
        if any(part in HIDDEN_FOLDERS for part in parts):
            raise ToolError("This folder is not available.")
        if parts and is_secret(parts[-1]):
            raise ToolError("Access to secret files is not allowed.")
        return full_path

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def all_files(self, folder):
        files = []
        for path in sorted(folder.rglob("*")):
            parts = path.relative_to(self.root).parts
            if any(part in HIDDEN_FOLDERS for part in parts) or is_secret(path.name):
                continue
            if path.is_symlink() and self.root not in path.resolve().parents:
                continue
            if path.is_file():
                files.append(path)
        return files


def read_text(path):
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ToolError("File is too large to read.")
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise ToolError("This is a binary file, not source code.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ToolError("File is not valid UTF-8 text.")


def list_files(repo, subdir=".", pattern="*"):
    folder = repo.safe_path(subdir)
    if not folder.is_dir():
        raise ToolError(f"Not a folder: {subdir}")
    files = [repo.relative(p) for p in repo.all_files(folder) if fnmatch.fnmatch(p.name, pattern)]
    return {"files": files[:MAX_FILES], "total": len(files), "truncated": len(files) > MAX_FILES}


def read_file(repo, path, start_line=1, end_line=None):
    file = repo.safe_path(path)
    if not file.is_file():
        raise ToolError(f"File not found: {path}")
    if end_line is not None and end_line < start_line:
        raise ToolError("end_line must be >= start_line.")

    lines = read_text(file).splitlines()
    total = len(lines)
    if total > 0 and start_line > total:
        raise ToolError(f"start_line {start_line} is past the end of the file ({total} lines).")

    wanted_end = end_line or total
    last = min(wanted_end, total, start_line + MAX_LINES - 1)
    text = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start_line, last + 1))
    return {"path": repo.relative(file), "start_line": start_line, "end_line": last,
            "total_lines": total, "truncated": last < wanted_end, "text": text}


def search_code(repo, query, max_results=20):
    matches = []
    for file in repo.all_files(repo.root):
        try:
            text = read_text(file)
        except ToolError:
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                matches.append({"path": repo.relative(file), "line": n, "snippet": line.strip()[:200]})
                if len(matches) == max_results:
                    return {"query": query, "matches": matches, "truncated": True}
    return {"query": query, "matches": matches, "truncated": False}


def run_tests(repo):
    try:
        done = subprocess.run(repo.test_command, cwd=repo.root, capture_output=True, text=True,
                              timeout=repo.test_timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"Tests did not finish in {repo.test_timeout} seconds.")
    except FileNotFoundError:
        raise ToolError(f"Test command not found: {repo.test_command[0]}")

    output = done.stdout + done.stderr
    passed = re.search(r"(\d+) passed", output)
    failed = re.search(r"(\d+) failed", output)
    return {"command": " ".join(repo.test_command),
            "exit_code": done.returncode,
            "passed": int(passed.group(1)) if passed else None,
            "failed": int(failed.group(1)) if failed else 0 if passed else None,
            "output_tail": output[-1500:]}


def load_progress(repo):
    if not repo.progress_file.is_file():
        return {}
    try:
        return json.loads(repo.progress_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def get_progress(repo):
    return {"repo": repo.root.name, "topics": load_progress(repo)}


def save_progress(repo, topic, verdict, note=""):
    progress = load_progress(repo)
    entry = progress.get(topic, {"attempts": 0, "history": []})
    entry["attempts"] += 1
    entry["last_verdict"] = verdict
    entry["history"] = (entry["history"] + [{"verdict": verdict, "note": note}])[-5:]
    progress[topic] = entry

    repo.progress_file.parent.mkdir(parents=True, exist_ok=True)
    repo.progress_file.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"topic": topic, "attempts": entry["attempts"], "last_verdict": verdict}


class ListFilesArgs(BaseModel):
    subdir: str = Field(".", description="Folder relative to the repository root")
    pattern: str = Field("*", description="File name pattern, e.g. *.py")


class ReadFileArgs(BaseModel):
    path: str = Field(min_length=1, description="File path relative to the repository root")
    start_line: int = Field(1, ge=1)
    end_line: int | None = Field(None, ge=1)


class SearchCodeArgs(BaseModel):
    query: str = Field(min_length=2, max_length=100, description="Text to find, case-insensitive")
    max_results: int = Field(20, ge=1, le=50)


class NoArgs(BaseModel):
    pass


class SaveProgressArgs(BaseModel):
    topic: str = Field(min_length=2, max_length=80, description="Short topic name, e.g. 'timeout handling'")
    verdict: Literal["correct", "partial", "incorrect"]
    note: str = Field("", max_length=300, description="What the student should review")


TOOLS = {
    "list_files": (ListFilesArgs, "List source files in the student's repository."),
    "read_file": (ReadFileArgs, f"Read a file with line numbers, at most {MAX_LINES} lines per call."),
    "search_code": (SearchCodeArgs, "Find lines that contain a text in the repository."),
    "run_tests": (NoArgs, "Run the repository's test suite and get passed/failed counts. "
                          "Use it to check what the student says about tests."),
    "get_progress": (NoArgs, "Get the student's results from previous sessions: topics, attempts, last verdict."),
    "save_progress": (SaveProgressArgs, "Save how the student answered on a topic."),
}


def tool_schemas():
    schemas = []
    for name, (args_model, description) in TOOLS.items():
        schemas.append({"type": "function", "function": {
            "name": name, "description": description, "parameters": args_model.model_json_schema()}})
    return schemas


def short_error(e):
    problems = []
    for err in e.errors():
        field_name = ".".join(str(x) for x in err["loc"]) or "args"
        problems.append(f"{field_name}: {err['msg']}")
    return "; ".join(problems)


def run_tool(repo, name, args):
    if name == "list_files":
        a = ListFilesArgs.model_validate(args)
        return list_files(repo, a.subdir, a.pattern)
    if name == "read_file":
        a = ReadFileArgs.model_validate(args)
        return read_file(repo, a.path, a.start_line, a.end_line)
    if name == "search_code":
        a = SearchCodeArgs.model_validate(args)
        return search_code(repo, a.query, a.max_results)
    if name == "run_tests":
        return run_tests(repo)
    if name == "get_progress":
        return get_progress(repo)
    if name == "save_progress":
        a = SaveProgressArgs.model_validate(args)
        return save_progress(repo, a.topic, a.verdict, a.note)
    raise ToolError(f"Unknown tool '{name}'.")


def execute(repo, name, args):
    try:
        result = {"ok": True, "result": run_tool(repo, name, args)}
    except ValidationError as e:
        result = {"ok": False, "error": "Invalid arguments: " + short_error(e)}
    except ToolError as e:
        result = {"ok": False, "error": str(e)}
    log.info("tool %s %s -> ok=%s", name, args, result["ok"])
    return result
