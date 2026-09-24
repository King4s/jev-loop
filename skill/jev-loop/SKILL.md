---
name: jev-loop
description: Build something with the Jev-driven build loop - interview the user, write the goal file for them, then run it (TypeSafe's Jev decides which role works next and when to stop; Claude Code does the work; a subagent reviews). Use when the user says "jev", "jev-loop", "kør loopen", "byg ... med jev", "lad Jev styre", or invokes /jev-loop - with or without a goal file or path. The user never has to remember paths or the goal format.
---

# jev-loop

The user should only have to say *what* they want. You work out the rest by asking
a few good questions, write the goal file yourself, and run the loop.
Talk to the user in their language (usually Danish).

## Phase 1 - Interview (skip what you already know)

Pull everything you can from the user's message and the current directory first.
Then ask only what is still unknown, in ONE `AskUserQuestion` call (max 4 questions,
concrete options with a recommended default first; the user can always pick "Other").
If *what to build* is completely missing, ask that first in plain chat.

What you need, and good defaults:

1. **Hvad skal bygges** - one sentence goal. Rewrite vague wishes into a concrete, testable goal.
2. **Hvor** - project folder. Default: a new folder `F:\AI-Projekter\<kort-navn>`
   (or the current working directory if the user is already in a project for this).
   If the folder already has code, the loop continues from it.
3. **Sprog / stack** - infer from the goal or existing files; ask only if unclear
   (e.g. Python / Node-TypeScript / other).
4. **Hvordan ved vi, at det virker** - this decides the `checks`. Propose them:
   Python -> `python -m pytest -q`; Node -> `npm test`; plus a build/lint/type-check
   when the stack has one. Deterministic checks are what keep the loop honest.
5. **Størrelse** - small (`max_turns` 10) / medium (20, default) / large (40).

Then **draft 3-6 acceptance criteria yourself**: concrete, checkable, including one
for error handling and one saying tests cover the criteria. Don't ask the user to write them.

## Phase 2 - Write the goal file and confirm

Write `<project folder>\goal.json`:

```json
{
  "goal": "...",
  "acceptance": ["...", "..."],
  "workdir": ".",
  "checks": ["python -m pytest -q"],
  "jev_model": "jev-latest",
  "jev_done_threshold": 0.8,
  "max_turns": 20,
  "max_consecutive_failures": 4,
  "check_timeout": 300,
  "roles": {
    "build": {"when": "Implementation code is missing or incomplete relative to the goal",
              "brief": "Implement the features. Write complete, working files. Do not write tests."},
    "test":  {"when": "Tests are missing or do not cover every acceptance criterion",
              "brief": "Write or extend tests that verify the acceptance criteria. Do not change implementation code."},
    "fix":   {"when": "Checks are failing with a concrete error message",
              "brief": "Read the failing check output and fix the root cause with the smallest correct change."}
  }
}
```

Adapt roles only if the task clearly needs it (e.g. a `docs` or `ui` role, each with a
clear `when`). `workdir` "." = the project folder itself.

Show the user a short summary (goal, criteria as bullets, checks, folder, size) and ask
for a go with `AskUserQuestion` ("Kør" / "Ret noget"). Apply corrections, then start.
If the user said to just go, skip the confirmation.

If a `goal.json` already exists in the folder, ask whether to reuse it, continue an
unfinished run (`loop_status`), or write a new one.

## Phase 3 - Run the loop

Jev (via the `jev-loop` MCP server) is the decider; you are the executor. Never decide
routing, "done" or giving up yourself - the server does, and it runs the checks.

1. `loop_start(goal_path)` -> `run_id`.
2. `loop_decide(run_id)` and act on `next`:
   - **`execute`**: do ONE focused step as `role`, following `brief` strictly
     (a `test` role does not touch implementation, etc.). Address `failing_checks`
     and `reviewer_missing` if present. Only write inside `workdir`. Then
     `loop_record_turn(run_id, notes, files, executor_ok)` - `notes` is 1-2 honest
     sentences, `files` relative to `workdir`, `executor_ok=false` if you could not do
     the step. Don't run the configured checks yourself; the server does.
   - **`review`**: spawn an independent `general-purpose` subagent (it must not see your
     reasoning). Give it the goal, acceptance criteria, workdir and check results; it
     reads the files (no edits) and answers strictly - passing checks are necessary, not
     sufficient - with `{"done": bool, "missing": [...]}`. Pass the verdict unchanged to
     `loop_record_review`, then follow that response's `next`.
   - **`stop`**: report `reason` (`goal_met` / `max_turns` / `escalate`), turns used,
     where the result is, and how to run it. On `escalate`, summarise what keeps failing.
3. Repeat until `stop`. One short line to the user per turn (turn, role, checks ok/fail).

If a tool returns `{"error": ...}`, fix the cause and retry that call; never bypass the
server. If the `jev-loop` tools are missing, tell the user to restart Claude Code (setup below).

## Setup (once)

From a clone of https://github.com/King4s/jev-loop run `.\install.ps1` (installs
dependencies, copies this skill, registers the `jev-loop` MCP server), then restart Claude Code.

`TYPESAFE_API_KEY` must be set in the user environment. Checks run model-written code in
a shell - for untrusted goals prefer a VM or container.
