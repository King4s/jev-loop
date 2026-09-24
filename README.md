# jev-loop

[![tests](https://github.com/King4s/jev-loop/actions/workflows/test.yml/badge.svg)](https://github.com/King4s/jev-loop/actions/workflows/test.yml)

En byggeloop, hvor **Jev beslutter** og **Claude Code eller Hermes udfører**.

[Jev](https://docs.typesafe.ai) (TypeSafe) er en hurtig beslutningsmodel, der svarer med
typede valg og sandsynligheder i stedet for tekst. I jev-loop afgør Jev for hver tur:

- **route**: hvilken rolle arbejder nu (`build`, `test`, `fix`, ...)
- **done**: sandsynligheden for, at målet er nået
- **recovery**: efter en fejl, om vi skal prøve igen, skifte rolle eller give op

Claude Code (eller Hermes) skriver koden. Serveren kører dine checks. En uafhængig subagent
reviewer, og **kun reviewet kan erklære opgaven færdig**.

## Kom i gang

Kræver Python 3.11+, [Claude Code](https://claude.com/claude-code) eller
[Hermes](https://hermes-agent.nousresearch.com) og en
[TypeSafe API-nøgle](https://docs.typesafe.ai), enten i miljøvariablen `TYPESAFE_API_KEY`
eller i filen `~/.config/jev-loop/typesafe_api_key` (kun læsbar for dig).

```powershell
# Windows
git clone https://github.com/King4s/jev-loop.git; cd jev-loop; .\install.ps1
```

```bash
# Linux / macOS / WSL (laver et venv i repoet)
git clone https://github.com/King4s/jev-loop.git ~/jev-loop && ~/jev-loop/install.sh
```

`install.sh` sætter begge harnesses op hvis de findes: skillen synces til
`~/.claude/skills/jev-loop/` og `~/.hermes/skills/jev-loop/`, og serveren registreres med
`claude mcp add` og `hermes mcp add`. Installeren slutter med `jev_mcp.py --check`, et lille
live-kald til Jev, der viser at afhængigheder, nøgle og netværk virker. Opdatering:
`git pull` og kør installeren igen.

I Hermes hedder værktøjerne `mcp_jev_loop_loop_start` osv.; start en ny session bagefter.
Ellers genstart Claude Code, og sig så bare hvad du vil have bygget:

> byg med jev: et lille værktøj der omdøber mine fotos efter optagelsesdato

eller skriv `/jev-loop` (Claude Code). Skillen stiller få konkrete spørgsmål (mappe, sprog,
hvordan det testes, størrelse), skriver acceptkriterierne og `goal.json` for dig, viser et
resumé og kører loopen, når du siger go.

## Sådan kører en tur

```
loop_decide ──► execute ──► loop_record_turn ──► (checks køres) ──┐
     ▲             │                                              │
     │             └──(Jev: checks OK og p_done ≥ tærskel)──► review ──► loop_record_review
     └────────────────────────────────────────────────────────────┘          │
                                                                    done ──► stop
```

Hårde stop: `max_turns`, `max_consecutive_failures`, eller Jev vælger `escalate`.
En tur er en fejl, hvis executoren melder fejl, en tidligere grøn check går i stykker, eller
intet flytter sig (ingen filer, samme fejl-output). En check, der blot endnu er rød, er ikke nok.
Alt logges i `runs/<id>.jsonl` (beslutningstapen, inkl. Jevs rå svar), og tilstanden i
`runs/<id>.state.json`, så en kørsel kan genoptages.

Hvad Jev ser: mål, acceptkriterier, projektets filliste, check-resultater, de seneste ture
og det sidste reviews mangler *sammen med turene siden*. Rå agent-output sendes ikke med;
Jev er svag over for støj.

## goal.json

Skillen skriver den for dig, men formatet er enkelt (se [goal.example.json](goal.example.json)):

| Felt | Betydning |
| --- | --- |
| `goal` | Målet i én sætning |
| `acceptance` | Liste af konkrete, tjekbare kriterier |
| `checks` | Shell-kommandoer i `workdir`; exit 0 = bestået. Jo flere deterministiske checks, jo ærligere loop |
| `workdir` | Projektmappen, relativt til goal-filen |
| `roles` | `when` = Jevs routing-kriterium, `brief` = instruks til executoren |
| `jev_model` | Standard `jev-latest` |
| `jev_done_threshold` | Hvornår Jev må sende til review (standard 0.8) |
| `max_turns`, `max_consecutive_failures`, `check_timeout` | Hårde grænser |

## MCP-værktøjer

| Værktøj | Gør |
| --- | --- |
| `loop_start(goal_path)` | Opretter en kørsel, kører checks én gang |
| `loop_decide(run_id)` | Spørger Jev; svarer `execute`, `review` eller `stop` |
| `loop_record_turn(run_id, notes, files, executor_ok)` | Registrerer turen og kører checks |
| `loop_record_review(run_id, done, missing)` | Registrerer reviewerens dom |
| `loop_status(run_id)` | Viser fase, historik og tape |

## Selvstændigt script: loop.py

`loop.py` er den oprindelige variant uden Claude Code: executor og reviewer er modeller
via OpenRouter. Kræver `OPENROUTER_API_KEY` og `TYPESAFE_API_KEY`.

```powershell
copy goal.example.json goal.json
python loop.py goal.json
```

Exit-koder: 0 = færdig, 1 = max_turns, 2 = kræver et menneske.
Bemærk: MCP-varianten er den vedligeholdte; `loop.py` sender endnu ikke fillisten eller
review-fremskridt til Jev.

## Udvikling

Repoet vedligeholdes af AI-agenter; reglerne står i [AGENTS.md](AGENTS.md).

```powershell
pip install -r requirements.txt
python -m pytest -q tests     # protokoltests med mocket Jev, ingen netværk
```

Versioner er datobaserede, `yyyy.mm.dd.ttmm`. Ny udgivelse (kræver ren working tree):

```powershell
.\release.ps1
```

Scriptet sætter `VERSION`, flytter `[Unreleased]` i [CHANGELOG.md](CHANGELOG.md) under den
nye version, committer, tagger `v<version>`, pusher og laver en GitHub-release.

## Sikkerhed

`checks` kører kommandoer i en shell på din maskine, og koden de tester er skrevet af en
model. Kør ukendte mål i en VM eller container. API-nøglen læses kun fra miljøet og
gemmes aldrig i repoet eller i tapen.

## Licens

[MIT](LICENSE)
