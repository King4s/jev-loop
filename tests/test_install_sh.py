"""install.sh: the Codex block installs the skill and registers the MCP server.

The real script runs in a sandbox HOME with stubbed harness CLIs (`codex`, `claude`,
`hermes`) and a no-op venv python, so no dependency, skill or MCP server is installed on
the machine running the tests. POSIX only - install.sh is a shell script.
"""
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="install.sh is a POSIX script")


def _stub(path, log):
    """A CLI that records how it was called and always succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "$0 $*" >> "{log}"\nexit 0\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def sandbox(tmp_path):
    """Repo copy + fake HOME + stubbed codex/claude/hermes + no-op venv python."""
    home = tmp_path / "home"
    home.mkdir()
    shutil.copy(ROOT / "install.sh", tmp_path / "install.sh")
    shutil.copytree(ROOT / "skill", tmp_path / "skill")
    log = tmp_path / "calls.log"
    _stub(tmp_path / ".venv" / "bin" / "python", log)
    for cli in ("codex", "claude", "hermes"):
        _stub(tmp_path / "bin" / cli, log)
    return tmp_path, home, log


def run(tmp_path, home, log, with_codex=True):
    binaries = tmp_path / "bin"
    path = f"{tmp_path}/.venv/bin:{binaries}:/usr/bin:/bin" if with_codex else f"{binaries}:/usr/bin:/bin"
    env = {"HOME": str(home), "PATH": path, "TYPESAFE_API_KEY": "dummy"}
    r = subprocess.run(["bash", "install.sh"], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    return r, log.read_text(encoding="utf-8") if log.exists() else ""


def test_skill_and_mcp_server_are_installed_for_codex(sandbox):
    tmp_path, home, log = sandbox
    r, calls = run(tmp_path, home, log)

    assert r.returncode == 0, r.stderr
    skill = home / ".agents" / "skills" / "jev-loop"
    assert (skill / "SKILL.md").is_file()
    assert (skill / "agents" / "openai.yaml").is_file(), "Codex skill metadata missing"

    venv_python = f"{tmp_path}/.venv/bin/python"
    assert "codex mcp remove jev-loop" in calls
    assert f"codex mcp add jev-loop -- {venv_python} {tmp_path}/jev_mcp.py" in calls


def test_missing_codex_is_not_an_error(sandbox):
    """No codex on PATH: skip that block, still set up the other harnesses, exit 0."""
    tmp_path, home, log = sandbox
    (tmp_path / "bin" / "codex").unlink()
    r, calls = run(tmp_path, home, log, with_codex=False)

    assert r.returncode == 0, r.stderr
    assert "codex not on PATH" in r.stdout
    assert "codex " not in calls, "the Codex block must not run when codex is missing"
    assert "claude mcp add jev-loop" in calls
    assert "hermes mcp add jev-loop" in calls
    assert not (home / ".agents").exists()