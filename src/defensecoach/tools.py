import fnmatch
import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("defensecoach.tools")

HIDDEN_FOLDERS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".idea", ".vscode"}
SECRET_FILES = [".env", ".env.*", "*.pem", "*.key", "id_rsa*", "*.p12", "secrets.*"]
MAX_FILES = 200
MAX_LINES = 300
MAX_FILE_SIZE = 1_000_000


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
    def __init__(self, folder):
        self.root = Path(folder).resolve()
        if not self.root.is_dir():
            raise ToolError(f"Repository folder not found: {folder}")

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


TOOLS = {
    "list_files": (ListFilesArgs, "List source files in the student's repository."),
    "read_file": (ReadFileArgs, f"Read a file with line numbers, at most {MAX_LINES} lines per call."),
    "search_code": (SearchCodeArgs, "Find lines that contain a text in the repository."),
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
