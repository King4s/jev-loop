# AGENTS.md - instructions for AI maintainers

This repository is maintained by AI agents, not by a human. The owner states
*what* they want in plain language (usually Danish) and never runs commands,
remembers paths, or edits config by hand. Do the whole job: change, test,
document, commit, release, push. Ask the owner only for real product decisions,
and answer them in Danish.

## What this is

- `jev_mcp.py` - MCP server (`jev-loop`). Jev (TypeSafe, `api.typesafe.ai/v1/systemone`)
  decides route / done / recovery; the server runs checks, hard stops and the tape.
  Claude Code is the executor. Run state: `runs/<id>.state.json`, tape: `runs/<id>.jsonl`.
- `skill/jev-loop/SKILL.md` - the Claude Code skill (interview -> goal.json -> loop).
  The installed copy lives in `~/.claude/skills/jev-loop/`; `install.ps1` syncs it.
- `loop.py` - older standalone variant (executor/reviewer via OpenRouter). Secondary.
- `tests/test_jev_mcp.py` - protocol tests with Jev mocked. No network, no key needed.

Jev API facts (verified against docs.typesafe.ai/api): response is
`{"answers": {id: {"type": "choice", "choice", "probabilities", "confidence"} |
{"type": "noul", "noul": p}}}`. Model `jev-latest`. Read the live docs
(https://docs.typesafe.ai/llms.txt) before changing questions or parsing.

## Every change

1. Make the change. Keep `jev_mcp.py` the source of truth for loop behaviour.
2. `python -m pytest -q tests` must pass. Add a test for new protocol behaviour.
3. If you changed `skill/jev-loop/SKILL.md`, also copy it to
   `~/.claude/skills/jev-loop/SKILL.md` (or run `.\install.ps1`).
4. Add a line under `## [Unreleased]` in `CHANGELOG.md` (Danish, sections
   `Tilføjet` / `Ændret` / `Rettet`).
5. Commit with a clear message ending in the agent's `Co-Authored-By` line.

## Releasing

Versions are date-based: `yyyy.mm.dd.ttmm` (local time, 24h, e.g. `2026.09.24.1422`).
Release after every meaningful change - there is no human to remember to do it.

```powershell
pwsh -File .\release.ps1
```

Requires a clean working tree and a non-empty `[Unreleased]` section. It writes
`VERSION`, moves `[Unreleased]` under the new version in `CHANGELOG.md`, commits,
tags `v<version>`, pushes and creates the GitHub release. Never edit `VERSION` by hand.

## Things only the owner can do

- GitHub OAuth scope changes (e.g. `gh auth refresh -s workflow`, needed before
  `.github/workflows/` files can be pushed). Tell the owner the one command to run.
- Setting `TYPESAFE_API_KEY` if it is missing.

## Don'ts

- Never commit `runs/`, `goal.json`, `workspace/` or any API key.
- Don't make Jev's decisions in code or in the skill; the server asks Jev.
- Don't send raw agent output to Jev; keep its state compact and structured.
