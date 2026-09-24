"""Protocol tests for jev_mcp.Run with Jev mocked out (no network, no API key)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_mcp as m  # noqa: E402

CHECK = "python -c \"import os,sys; sys.exit(0 if os.path.exists('ok.txt') else 1)\""


@pytest.fixture
def goal(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "RUNS", tmp_path / "runs")
    g = tmp_path / "goal.json"
    g.write_text(json.dumps({
        "goal": "make ok.txt", "workdir": "ws", "checks": [CHECK],
        "roles": {"build": {"when": "a", "brief": "b"}, "fix": {"when": "c", "brief": "d"}},
        "max_consecutive_failures": 2,
    }), encoding="utf-8")
    return g


def fake_jev(route="build", recovery="retry", p_done=None, seen=None):
    def jev(model, state, qs):
        if seen is not None:
            seen.append((state, qs))
        done = p_done if p_done is not None else (0.9 if state["all_checks_pass"] else 0.1)
        a = {"route": {"type": "choice", "choice": route, "confidence": 0.8,
                       "probabilities": {"build": 0.7, "fix": 0.3}},
             "done": {"type": "noul", "noul": done}}
        if "recovery" in qs:
            a["recovery"] = {"type": "choice", "choice": recovery, "probabilities": {}}
        return {"model": "fake", "answers": a}
    return jev


def test_full_run_to_goal_met(goal, monkeypatch):
    monkeypatch.setattr(m, "jev", fake_jev())
    run = m.Run.create(goal)
    assert run.s["checks_ok"] is False

    d = m.Run(run.id).decide()
    assert (d["next"], d["role"]) == ("execute", "build")
    Path(run.cfg["workdir"], "ok.txt").write_text("x")
    assert m.Run(run.id).record_turn("made it", ["ok.txt"], True)["checks_ok"] is True

    assert m.Run(run.id).decide()["next"] == "review"
    d = m.Run(run.id).record_review(False, ["needs more"])
    assert d["next"] == "execute" and d["reviewer_missing"] == ["needs more"]
    m.Run(run.id).record_turn("did more", [], True)

    assert m.Run(run.id).decide()["next"] == "review"
    stop = m.Run(run.id).record_review(True, [])
    assert stop["reason"] == "goal_met"
    with pytest.raises(RuntimeError, match="already stopped"):
        m.Run(run.id).decide()


def test_route_wins_over_retry(goal, monkeypatch):
    run = m.Run.create(goal)
    monkeypatch.setattr(m, "jev", fake_jev(route="build"))
    m.Run(run.id).decide()
    m.Run(run.id).record_turn("nothing", [], True)  # check fails -> fails=1, last_role=build
    monkeypatch.setattr(m, "jev", fake_jev(route="fix", recovery="retry"))
    assert m.Run(run.id).decide()["role"] == "fix"


def test_reroute_moves_away_from_last_role(goal, monkeypatch):
    monkeypatch.setattr(m, "jev", fake_jev(route="build", recovery="reroute"))
    run = m.Run.create(goal)
    m.Run(run.id).decide()
    m.Run(run.id).record_turn("nothing", [], True)
    assert m.Run(run.id).decide()["role"] == "fix"


def test_escalate_and_max_failures(goal, monkeypatch):
    monkeypatch.setattr(m, "jev", fake_jev(recovery="escalate"))
    run = m.Run.create(goal)
    m.Run(run.id).decide()
    m.Run(run.id).record_turn("nothing", [], True)
    assert m.Run(run.id).decide()["reason"] == "escalate"

    monkeypatch.setattr(m, "jev", fake_jev(recovery="retry"))
    run = m.Run.create(goal)
    for _ in range(2):
        m.Run(run.id).decide()
        m.Run(run.id).record_turn("nothing", [], False)

    def boom(*a):
        raise AssertionError("Jev must not be called after max failures")
    monkeypatch.setattr(m, "jev", boom)
    assert m.Run(run.id).decide()["reason"] == "escalate"


def test_jev_sees_files_and_review_progress(goal, monkeypatch):
    seen = []
    monkeypatch.setattr(m, "jev", fake_jev(seen=seen))
    run = m.Run.create(goal)
    Path(run.cfg["workdir"], "ok.txt").write_text("x")
    Path(run.cfg["workdir"], "__pycache__").mkdir()
    Path(run.cfg["workdir"], "__pycache__", "x.pyc").write_text("x")
    m.Run(run.id).decide()
    m.Run(run.id).record_turn("t1", ["ok.txt"], True)
    m.Run(run.id).decide()
    m.Run(run.id).record_review(False, ["add docs"])
    m.Run(run.id).record_turn("added docs", ["README.md"], True)
    m.Run(run.id).decide()

    state = seen[-1][0]
    assert state["project_files"] == ["ok.txt"]
    assert state["last_review"]["missing"] == ["add docs"]
    assert [t["notes"] for t in state["last_review"]["turns_since_review"]] == ["added docs"]


def test_wrong_step_is_rejected(goal, monkeypatch):
    monkeypatch.setattr(m, "jev", fake_jev())
    run = m.Run.create(goal)
    with pytest.raises(RuntimeError, match="wrong step"):
        m.Run(run.id).record_turn("x", [], True)
    m.Run(run.id).decide()
    with pytest.raises(RuntimeError, match="wrong step"):
        m.Run(run.id).decide()


def test_max_turns(goal, monkeypatch):
    monkeypatch.setattr(m, "jev", fake_jev(recovery="retry"))
    g = json.loads(goal.read_text())
    g.update(max_turns=1, max_consecutive_failures=99)
    goal.write_text(json.dumps(g))
    run = m.Run.create(goal)
    m.Run(run.id).decide()
    m.Run(run.id).record_turn("x", [], True)
    assert m.Run(run.id).decide()["reason"] == "max_turns"


def test_mcp_server_exposes_tools():
    import asyncio
    names = {t.name for t in asyncio.run(m.build_server().list_tools())}
    assert names == {"loop_start", "loop_decide", "loop_record_review", "loop_record_turn", "loop_status"}
