"""jev-loop as an MCP server: Jev decides, Claude Code does the work.

The server owns the parts that must not depend on the executor's judgement:
Jev's decisions (route / done / recovery), running the checks, the hard stops
and the decision tape. The client (Claude Code, driven by the jev-loop skill)
writes the code and runs the review.

Protocol per turn:
  loop_decide        -> next = "execute" | "review" | "stop"
  (review)           -> loop_record_review -> next = "execute" | "stop"
  (execute role)     -> loop_record_turn   -> checks run, then loop_decide again

Needs TYPESAFE_API_KEY in the environment.
Run:   python jev_mcp.py            (stdio MCP server)
"""
import json
import os
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
RUNS = ROOT / "runs"
API = "https://api.typesafe.ai/v1/systemone"
RETRY_STATUS = {429, 529}
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "dev"


# ---------- Jev ----------

def jev(model, state, questions, retries=4):
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is not set in the MCP server's environment.")
    for attempt in range(retries + 1):
        r = requests.post(
            API, timeout=60,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "state": state, "questions": questions},
        )
        if r.status_code in RETRY_STATUS and attempt < retries:
            time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Jev HTTP {r.status_code}: {r.text[:500]}")
        return r.json()


# ---------- checks ----------

def run_checks(cmds, workdir, timeout):
    results = []
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout)
            results.append({"cmd": cmd, "ok": r.returncode == 0,
                            "out": (r.stdout + r.stderr)[-2000:]})
        except subprocess.TimeoutExpired:
            results.append({"cmd": cmd, "ok": False, "out": "TIMEOUT"})
    return results


SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", ".git", ".pytest_cache"}


def list_files(workdir, limit=200):
    """Relative paths of project files, so Jev knows what already exists."""
    out = []
    for p in sorted(Path(workdir).rglob("*")):
        parts = p.relative_to(workdir).parts
        if p.is_dir() or any(x in SKIP_DIRS or x.startswith(".") for x in parts):
            continue
        out.append(p.relative_to(workdir).as_posix())
        if len(out) >= limit:
            out.append("... (more files omitted)")
            break
    return out


# ---------- a run ----------

class Run:
    """One loop run. State lives in runs/<id>.state.json, events in runs/<id>.jsonl."""

    def __init__(self, run_id):
        self.id = run_id
        self.state_path = RUNS / f"{run_id}.state.json"
        self.tape_path = RUNS / f"{run_id}.jsonl"
        if not self.state_path.exists():
            raise KeyError(f"unknown run_id '{run_id}'")
        self.s = json.loads(self.state_path.read_text(encoding="utf-8"))

    @classmethod
    def create(cls, goal_path):
        p = Path(goal_path).resolve()
        cfg = json.loads(p.read_text(encoding="utf-8"))
        for k in ("goal", "roles"):
            if k not in cfg:
                raise ValueError(f"goal file is missing '{k}'")
        workdir = (p.parent / cfg.get("workdir", "workspace")).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        cfg["workdir"] = str(workdir)
        cfg.setdefault("jev_model", "jev-latest")
        cfg.setdefault("jev_done_threshold", 0.8)
        cfg.setdefault("max_turns", 20)
        cfg.setdefault("max_consecutive_failures", 4)
        cfg.setdefault("check_timeout", 300)

        RUNS.mkdir(exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        n = 1
        while (RUNS / f"{run_id}.state.json").exists():
            n += 1
            run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        (RUNS / f"{run_id}.state.json").write_text("{}", encoding="utf-8")
        run = cls(run_id)
        checks = run_checks(cfg.get("checks", []), workdir, cfg["check_timeout"])
        run.s = {"cfg": cfg, "turn": 0, "phase": "decide", "checks": checks,
                 "checks_ok": all(c["ok"] for c in checks),  # no checks -> True
                 "fails": 0, "last_role": None, "pending_role": None,
                 "history": [], "review": None, "stopped": None}
        run.save()
        run.log("start", goal=cfg["goal"], workdir=cfg["workdir"], goal_file=str(p))
        return run

    # --- persistence ---
    def save(self):
        self.state_path.write_text(json.dumps(self.s, ensure_ascii=False, indent=1), encoding="utf-8")

    def log(self, kind, **kw):
        rec = {"t": time.strftime("%H:%M:%S"), "kind": kind, **kw}
        with open(self.tape_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    @property
    def cfg(self):
        return self.s["cfg"]

    # --- helpers ---
    def _expect(self, *phases):
        if self.s["stopped"]:
            raise RuntimeError(f"run already stopped: {self.s['stopped']}")
        if self.s["phase"] not in phases:
            raise RuntimeError(f"wrong step: run is in phase '{self.s['phase']}', expected {phases}")

    def _stop(self, reason, **kw):
        self.s["stopped"] = reason
        self.s["phase"] = "stopped"
        self.log("stop", reason=reason, turn=self.s["turn"], **kw)
        self.save()
        return {"next": "stop", "reason": reason, "turn": self.s["turn"],
                "tape": str(self.tape_path), **kw}

    def _execute(self, role):
        self.s["pending_role"] = role
        self.s["phase"] = "execute"
        self.save()
        spec = self.cfg["roles"][role]
        return {"next": "execute", "turn": self.s["turn"], "role": role, "brief": spec["brief"],
                "workdir": self.cfg["workdir"], "reviewer_missing": (self.s["review"] or {}).get("missing"),
                "failing_checks": [c for c in self.s["checks"] if not c["ok"]]}

    def summary(self):
        return {"run_id": self.id, "turn": self.s["turn"], "phase": self.s["phase"],
                "stopped": self.s["stopped"], "checks_ok": self.s["checks_ok"],
                "consecutive_fails": self.s["fails"], "last_review": self.s["review"],
                "history": self.s["history"], "tape": str(self.tape_path)}

    # --- protocol ---
    def decide(self):
        self._expect("decide")
        cfg, s = self.cfg, self.s
        if s["turn"] >= cfg["max_turns"]:
            return self._stop("max_turns")
        if s["fails"] >= cfg["max_consecutive_failures"]:
            return self._stop("escalate", why="max_consecutive_failures reached")
        s["turn"] += 1
        roles = cfg["roles"]

        # Compact, structured state. No raw agent output: Jev is weak on distractors.
        state = {
            "goal": cfg["goal"],
            "acceptance": cfg.get("acceptance", []),
            "turn": s["turn"],
            "project_files": list_files(cfg["workdir"]),
            "all_checks_pass": s["checks_ok"],
            "checks": [{"cmd": c["cmd"], "ok": c["ok"], "tail": c["out"][-300:]} for c in s["checks"]],
            # What the last review found missing, and the turns taken since, so Jev can
            # judge whether it has been addressed (a stale list alone keeps p_done low).
            "last_review": {"missing": s["review"]["missing"],
                            "turns_since_review": s["history"][s["review"]["at_history"]:]}
                           if s["review"] else None,
            "recent_turns": [{k: h[k] for k in ("turn", "role", "files", "notes", "checks_ok")}
                             for h in s["history"][-5:]],
        }
        qs = {
            "route": {"type": "choice",
                      "instructions": "Which agent should take the next turn toward the `goal`?",
                      "criteria": {k: v["when"] for k, v in roles.items()}},
            "done": {"type": "noul",
                     "instructions": "Is the `goal` fully met: every check passing, every "
                                     "`acceptance` criterion satisfied, and (if `last_review` is set) "
                                     "every item in `last_review.missing` addressed by the turns in "
                                     "`last_review.turns_since_review`?"},
        }
        if s["fails"]:
            qs["recovery"] = {"type": "choice",
                              "instructions": "The last turn failed (see `recent_turns` and `checks`). "
                                              "What is the best recovery?",
                              "criteria": {
                                  "retry": "Same agent again; the failure looks transient or nearly fixed",
                                  "reroute": "A different agent is better suited to fix this",
                                  "escalate": "Repeated failures with no real progress; a human is needed"}}

        raw = jev(cfg["jev_model"], state, qs)
        a = raw["answers"]
        route = a["route"]
        role, p_done = route["choice"], float(a["done"]["noul"])
        decision = {"turn": s["turn"], "route": role, "route_conf": route.get("confidence"),
                    "p_done": round(p_done, 3), "model": raw.get("model")}

        if s["fails"]:
            rec = a["recovery"]["choice"]
            decision["recovery"] = rec
            # 'route' already saw the failure and stays the primary decision; 'retry' must not
            # override it (a failed build turn is often fixed by routing to another role).
            if rec == "reroute" and role == s["last_role"] and len(roles) > 1:
                probs = {k: v for k, v in route["probabilities"].items() if k != s["last_role"]}
                role = max(probs, key=probs.get)
            decision["role"] = role
            self.log("decide", **decision, jev_raw=raw)
            if rec == "escalate":
                return self._stop("escalate", why="Jev chose escalate")
        else:
            decision["role"] = role
            self.log("decide", **decision, jev_raw=raw)

        if role not in roles:
            self.log("warn", msg=f"unknown role '{role}', falling back")
            role = next(iter(roles))

        # Cascade: cheap Jev filter first; the review is the only way to finish.
        if s["checks_ok"] and p_done >= cfg["jev_done_threshold"]:
            s["pending_role"] = role
            s["phase"] = "review"
            self.save()
            return {"next": "review", "turn": s["turn"], "p_done": round(p_done, 3),
                    "goal": cfg["goal"], "acceptance": cfg.get("acceptance", []),
                    "workdir": cfg["workdir"], "checks": s["checks"]}
        return self._execute(role)

    def record_review(self, done, missing):
        self._expect("review")
        self.log("review", done=done, missing=missing)
        if done:
            return self._stop("goal_met", executor_turns=len(self.s["history"]))
        self.s["review"] = {"missing": [str(m)[:300] for m in missing][:10] or ["reviewer said not done (no details)"],
                            "at_history": len(self.s["history"])}
        return self._execute(self.s["pending_role"])

    def record_turn(self, notes, files, executor_ok):
        self._expect("execute")
        s, cfg = self.s, self.cfg
        role = s["pending_role"]
        checks = run_checks(cfg.get("checks", []), cfg["workdir"], cfg["check_timeout"])
        checks_ok = executor_ok and all(c["ok"] for c in checks)
        s["checks"], s["checks_ok"] = checks, checks_ok
        s["fails"] = 0 if checks_ok else s["fails"] + 1
        s["last_role"], s["pending_role"], s["phase"] = role, None, "decide"
        h = {"turn": s["turn"], "role": role, "files": files, "notes": notes[:300], "checks_ok": checks_ok}
        s["history"].append(h)
        self.log("turn", **h)
        self.save()
        return {"turn": s["turn"], "checks_ok": checks_ok, "consecutive_fails": s["fails"],
                "checks": [{"cmd": c["cmd"], "ok": c["ok"], "out": c["out"][-1200:]} for c in checks],
                "next": "call loop_decide"}


# ---------- MCP ----------

def build_server():
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("jev-loop", version=VERSION, instructions=(
        "Jev-driven build loop. Use with the jev-loop skill. Call loop_start, then repeat "
        "loop_decide -> (review -> loop_record_review) -> execute -> loop_record_turn "
        "until a response has next='stop'. Never skip a step or invent a decision."))

    def safe(fn):
        try:
            return fn()
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    def loop_start(goal_path: str) -> dict:
        """Start a run from a goal JSON file (goal, acceptance, workdir, checks, roles...).
        Runs the checks once and returns the run_id. Next: loop_decide."""
        def go():
            run = Run.create(goal_path)
            c = run.cfg
            return {"run_id": run.id, "workdir": c["workdir"], "goal": c["goal"],
                    "acceptance": c.get("acceptance", []), "checks": c.get("checks", []),
                    "roles": {k: v["brief"] for k, v in c["roles"].items()},
                    "max_turns": c["max_turns"], "tape": str(run.tape_path),
                    "next": "call loop_decide"}
        return safe(go)

    @mcp.tool()
    def loop_decide(run_id: str) -> dict:
        """Ask Jev for the next step. Returns next='execute' (do the role's work in workdir,
        then loop_record_turn), next='review' (run an independent review, then
        loop_record_review) or next='stop' (report the reason to the user)."""
        return safe(lambda: Run(run_id).decide())

    @mcp.tool()
    def loop_record_review(run_id: str, done: bool, missing: list[str]) -> dict:
        """Record the reviewer's verdict. done=true ends the run as goal_met; otherwise
        'missing' is fed back into the loop and next='execute' follows."""
        return safe(lambda: Run(run_id).record_review(done, missing))

    @mcp.tool()
    def loop_record_turn(run_id: str, notes: str, files: list[str], executor_ok: bool = True) -> dict:
        """Record the executed turn: notes (1-2 sentences), files written (relative to
        workdir). Set executor_ok=false if you could not complete the step. The server
        runs the checks and returns them. Next: loop_decide."""
        return safe(lambda: Run(run_id).record_turn(notes, files, executor_ok))

    @mcp.tool()
    def loop_status(run_id: str) -> dict:
        """Current phase, checks, history and tape path of a run."""
        return safe(lambda: Run(run_id).summary())

    return mcp


if __name__ == "__main__":
    build_server().run()
