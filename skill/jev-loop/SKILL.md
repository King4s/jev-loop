---
name: jev-loop
description: Build something with the Jev-driven build loop - interview the user, write the goal file for them, then run it (TypeSafe's Jev decides which role works next and when to stop; Claude Code, Codex or Hermes does the work; a subagent reviews). Use when the user says "jev", "jev-loop", "kør loopen", "byg ... med jev", "lad Jev styre", or invokes /jev-loop - with or without a goal file or path. The user never has to remember paths or the goal format.
---

# jev-loop

The user should only have to say *what* they want. You work out the rest by asking
a few good questions, write the goal file yourself, and run the loop.
Talk to the user in their language (usually Danish).

## Phase 1 - Interview (skip what you already know)

Pull everything you can from the user's message and the current directory first.
Then ask only what is still unknown, in ONE structured question call (max 4-5 questions,
concrete options with a recommended default first; the user can always pick "Other").
Use `clarify` in Hermes, `AskUserQuestion` in Claude Code; in Codex, ask in plain chat
(it has no question tool by default) and keep it to one short list of questions.
If *what to build* is completely missing, ask that first in plain chat.

What you need, and good defaults:

1. **What to build** - one sentence goal. Rewrite vague wishes into a concrete, testable goal.
2. **Where** - project folder. Default: a new folder for this project next to where the user
   keeps projects (Windows: `F:\AI-Projekter\<short-name>`; otherwise the current working
   directory). If the folder already has code, the loop continues from it.
3. **Language / stack** - infer from the goal or existing files; ask only if unclear
   (e.g. Python / Node-TypeScript / other).
4. **How we know it works** - this decides the `checks`. Propose them:
   Python -> `python -m pytest -q`; Node -> `npm test`; plus a build/lint/type-check
   when the stack has one. Deterministic checks are what keep the loop honest.
5. **Size** - small (`max_turns` 10) / medium (20, default) / large (40).

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
for a go with the same question tool ("Go" / "Change something", in the user's language). Apply corrections, then start.
If the user said to just go, skip the confirmation.

If a `goal.json` already exists in the folder, ask whether to reuse it, continue an
unfinished run (`loop_status`), or write a new one.

## Phase 3 - Run the loop

Jev (via the `jev-loop` MCP server) is the decider; you are the executor. Never decide
routing, "done" or giving up yourself - the server does, and it runs the checks.
In Hermes the tools are named `mcp_jev_loop_loop_start`, `mcp_jev_loop_loop_decide`,
`mcp_jev_loop_loop_record_turn`, `mcp_jev_loop_loop_record_review`, `mcp_jev_loop_loop_status`;
in Claude Code and Codex they come from the `jev-loop` MCP server as `loop_start`,
`loop_decide`, `loop_record_turn`, `loop_record_review` and `loop_status`.

1. `loop_start(goal_path)` -> `run_id`.
2. `loop_decide(run_id)` and act on `next`:
   - **`execute`**: do ONE focused step as `role`, following `brief` strictly
     (a `test` role does not touch implementation, etc.). Address `failing_checks`
     and `reviewer_missing` if present. Only write inside `workdir`. Then
     `loop_record_turn(run_id, notes, files, executor_ok)` - `notes` is 1-2 honest
     sentences, `files` relative to `workdir`, `executor_ok=false` if you could not do
     the step. Don't run the configured checks yourself; the server does.
   - **`review`**: get an independent review in a context that cannot see your reasoning:
     `delegate_task` in Hermes, the `general-purpose` Task agent in Claude Code, or a
     fresh read-only process in Codex:
     `codex exec -s read-only -C <workdir> -o verdict.json "<review prompt>"` - a new
     process with no shared context, which cannot edit files; the verdict lands in
     `verdict.json` so it can be passed on unchanged. Give it the goal, acceptance
     criteria, workdir and check results; it reads the files (no edits) and answers
     strictly - passing checks are necessary, not sufficient - with
     `{"done": bool, "missing": [...]}`. Pass the verdict unchanged to
     `loop_record_review`, then follow that response's `next`.
   - **`stop`**: report `reason` (`goal_met` / `max_turns` / `escalate`), turns used,
     where the result is, and how to run it. On `escalate`, summarise what keeps failing.
3. Repeat until `stop`. One short line to the user per turn (turn, role, checks ok/fail).

### When the run keeps answering `execute`

The server decides; you never route yourself. But the server's two facts about a
reviewer are worth knowing, because a run can sit in `execute` with nothing left to do:

- After `loop_record_review(done=false)` the server hands out the queued role's turn.
  Record it with `loop_record_turn` **before** the next `loop_decide`, or that call fails
  with `wrong step: run is in phase 'execute'`.
- A reviewer is offered when Jev thinks the goal is met, when the same role keeps running
  with unchanged green checks (`stall_turns`), or when `review_turns` (default 3) green
  executor turns have passed since the last review - or since the start, if no reviewer
  has looked yet. A run whose executor keeps doing real work never stalls (every turn
  changes the check output) and Jev's `p_done` can sit below the threshold for the whole
  run, so the third path is what gets such a run in front of a reviewer at all; Jev still
  answers `review_now` and decides.
- If `loop_decide` keeps returning `execute` with nothing left to do, record an audit turn
  (`files: []`) whose note says plainly what is finished and that only the verdict remains.
  That is evidence Jev can act on; process narration is not.
- Keep `notes` short and lead with the change and its evidence, not the story: Jev sees
  only the first `NOTE_CHARS` (600) characters of each note, and the state is built to
  keep him away from everything else.

If a tool returns `{"error": ...}`, fix the cause and retry that call; never bypass the
server. If the `jev-loop` tools are missing, tell the user to restart the harness so it
picks up the new MCP server (setup below).

## Setup (once)

From a clone of https://github.com/King4s/jev-loop run `./install.sh` (Linux, macOS, WSL)
or `.\install.ps1` (Windows). Both install dependencies, sync this skill and register the
`jev-loop` MCP server for every harness they find on PATH:

| Harness | Skill | MCP |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/jev-loop/` | `claude mcp add` |
| Codex | `~/.agents/skills/jev-loop/` | `codex mcp add` (`~/.codex/config.toml`) |
| Hermes | `~/.hermes/skills/jev-loop/` | `hermes mcp add` |

Then restart the harness / start a new session. In Codex, the skill is invoked with
`/skills` or `$jev-loop` (and it also triggers on the description).

The TypeSafe key goes in the environment as `TYPESAFE_API_KEY` or in
`~/.config/jev-loop/typesafe_api_key` (mode 600); the server reads both. In Hermes the key
must be in the key file, or in `~/.hermes/.env` so the server's `env` block can resolve it -
a stdio MCP subprocess does not inherit your shell. Checks run model-written code in a
shell - for untrusted goals prefer a VM or container.
