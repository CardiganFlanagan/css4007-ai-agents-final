import os

import pytest

from defensecoach.tools import Repo, ToolError, execute, list_files, read_file, search_code, tool_schemas


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "client.py").write_text(
        "def call_llm():\n    try:\n        return send()\n    except TimeoutError:\n        raise\n",
        encoding="utf-8")
    (root / "src" / "big.py").write_text("\n".join(f"x{i} = {i}" for i in range(1, 501)), encoding="utf-8")
    (root / "README.md").write_text("# Demo\nRetry logic lives in client.py\n", encoding="utf-8")
    (root / ".env").write_text("LLM_API_KEY=sk-secret\n", encoding="utf-8")
    (root / ".env.example").write_text("LLM_API_KEY=\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "site.py").write_text("x = 1\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\x00\x00binary")
    (tmp_path / "outside.txt").write_text("secret outside repo", encoding="utf-8")
    return Repo(root)


def test_list_files_hides_secrets_and_service_folders(repo):
    files = list_files(repo)["files"]
    assert "src/client.py" in files and "README.md" in files and ".env.example" in files
    assert ".env" not in files
    assert not any(f.startswith((".git/", ".venv/")) for f in files)


def test_list_files_pattern_and_subdir(repo):
    assert list_files(repo, "src", "*.py")["files"] == ["src/big.py", "src/client.py"]


def test_read_file_returns_numbered_range(repo):
    result = read_file(repo, "src/client.py", 2, 4)
    assert result["text"].splitlines() == ["2:     try:", "3:         return send()", "4:     except TimeoutError:"]
    assert result["total_lines"] == 5 and not result["truncated"]


def test_read_file_is_capped(repo):
    result = read_file(repo, "src/big.py")
    assert result["end_line"] == 300 and result["truncated"]


@pytest.mark.parametrize("path", ["../outside.txt", "src/../../outside.txt", "/etc/passwd", "C:/Windows/win.ini"])
def test_paths_outside_repo_are_rejected(repo, path):
    with pytest.raises(ToolError, match="outside|relative"):
        read_file(repo, path)


@pytest.mark.parametrize("path", [".env", "src/../.env", ".git/config", ".venv/lib/site.py"])
def test_secret_and_service_files_are_rejected(repo, path):
    with pytest.raises(ToolError, match="secret|not available"):
        read_file(repo, path)


def test_symlink_escape_is_blocked(repo, tmp_path):
    link = repo.root / "sneaky.txt"
    try:
        os.symlink(tmp_path / "outside.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this system")
    with pytest.raises(ToolError, match="outside"):
        read_file(repo, "sneaky.txt")
    assert "sneaky.txt" not in list_files(repo)["files"]


def test_missing_and_binary_files_give_clear_errors(repo):
    with pytest.raises(ToolError, match="not found"):
        read_file(repo, "src/nope.py")
    with pytest.raises(ToolError, match="binary"):
        read_file(repo, "logo.png")


def test_search_code_is_case_insensitive_and_skips_secrets(repo):
    found = search_code(repo, "timeouterror")["matches"]
    assert found == [{"path": "src/client.py", "line": 4, "snippet": "except TimeoutError:"}]
    assert search_code(repo, "sk-secret")["matches"] == []


def test_search_code_respects_limit(repo):
    result = search_code(repo, "x", max_results=5)
    assert len(result["matches"]) == 5 and result["truncated"]


def test_execute_validates_arguments_instead_of_crashing(repo):
    bad = [
        ("read_file", {"path": "src/client.py", "start_line": -1}),
        ("read_file", {}),
        ("search_code", {"query": "x" * 500}),
        ("list_files", {"subdir": 123}),
    ]
    for name, args in bad:
        result = execute(repo, name, args)
        assert result["ok"] is False and result["error"].startswith("Invalid arguments"), (name, args)

    reversed_lines = execute(repo, "read_file", {"path": "src/client.py", "start_line": 4, "end_line": 2})
    assert reversed_lines == {"ok": False, "error": "end_line must be >= start_line."}


def test_execute_reports_tool_errors_and_unknown_tools(repo):
    assert execute(repo, "read_file", {"path": "../outside.txt"}) == {"ok": False, "error": "Path is outside the repository."}
    assert execute(repo, "delete_everything", {})["error"] == "Unknown tool 'delete_everything'."
    ok = execute(repo, "search_code", {"query": "retry"})
    assert ok["ok"] and ok["result"]["matches"][0]["path"] == "README.md"


def test_tool_schemas_match_registered_tools():
    names = [s["function"]["name"] for s in tool_schemas()]
    assert names == ["list_files", "read_file", "search_code", "run_tests", "get_progress", "save_progress"]
    read = next(s for s in tool_schemas() if s["function"]["name"] == "read_file")
    assert read["function"]["parameters"]["required"] == ["path"]
