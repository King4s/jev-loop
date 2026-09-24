# Changelog

Versioner er datobaserede: `yyyy.mm.dd.ttmm` (lokal tid for udgivelsen).
Nye udgivelser laves med `.\release.ps1`.

## [Unreleased]

### Ændret
- `AGENTS.md` lister hvilke maskiner jev-loop er installeret på.

## [2026.09.24.1436] - 2026-09-24

### Rettet
- `install.ps1`: stien til nøglefilen var ødelagt (`\t` blev til et tabulatortegn).
- `install.sh` virker også uden `python3-venv`/ensurepip (henter pip fra bootstrap.pypa.io).

## [2026.09.24.1435] - 2026-09-24

### Tilføjet
- `install.sh` til Linux/macOS (venv, skill, MCP-registrering, live-tjek).
- `jev_mcp.py --check`: lille live-kald til Jev som sundhedstjek; installerne kører det til sidst.
- API-nøglen kan ligge i `~/.config/jev-loop/typesafe_api_key`, når miljøvariablen ikke er sat.

### Rettet
- Testene bruger den kørende Python i stedet for `python` fra PATH.

## [2026.09.24.1430] - 2026-09-24

### Tilføjet
- GitHub Actions CI: testene køres på Ubuntu og Windows ved hvert push.

## [2026.09.24.1425] - 2026-09-24

### Tilføjet
- `AGENTS.md` (+ `CLAUDE.md`): instrukser til AI-vedligeholdere - repoet vedligeholdes af AI, ikke af et menneske.

### Ændret
- `release.ps1` afviser en udgivelse med tom `[Unreleased]`-sektion.

## [2026.09.24.1422] - 2026-09-24

Første udgivelse.

### Tilføjet
- `jev_mcp.py`: MCP-server med værktøjerne `loop_start`, `loop_decide`,
  `loop_record_turn`, `loop_record_review` og `loop_status`. Serveren ejer Jev-kald,
  checks, hårde stop og beslutningstapen; Claude Code er executor.
- Skill `jev-loop`: interviewer brugeren, skriver `goal.json` og kører loopen.
- `install.ps1` (skill + MCP-registrering) og `release.ps1` (datoversion, tag, GitHub-release).
- Protokoltests med mocket Jev (`tests/`).

### Rettet
- Jev kaldes direkte på `api.typesafe.ai/v1/systemone` med `TYPESAFE_API_KEY`;
  svarformatet er verificeret mod dokumentationen (i stedet for gættet parsing).
- `recovery=retry` overskriver ikke længere Jevs `route`-valg.
- `reroute` tvinger nu en anden rolle, hvis `route` peger på den samme.
- Jev ser projektets filliste, så den ikke beder om at bygge det, der findes.
- Reviewerens mangler vises sammen med turene siden reviewet, så en løst mangel ikke
  holder `p_done` nede og får loopen til at køre i ring.
- Ingen Jev-kald, når `max_consecutive_failures` allerede er nået.
- Konsistent `checks_ok`, når der ikke er konfigureret checks.
