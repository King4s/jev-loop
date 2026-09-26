# One-time / update setup for Claude Code, Codex and Hermes on Windows: installs
# dependencies, copies the skill and registers the MCP server at user scope. Safe to
# run again after updates.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -q -r requirements.txt

$skillDir = Join-Path $HOME ".claude\skills\jev-loop"
New-Item -ItemType Directory -Force $skillDir | Out-Null
Copy-Item skill\jev-loop\SKILL.md $skillDir -Force
Write-Host "Skill installed: $skillDir"

$server = Join-Path $PSScriptRoot "jev_mcp.py"
if (Get-Command claude -ErrorAction SilentlyContinue) {
    claude mcp remove jev-loop --scope user 2>$null | Out-Null
    claude mcp add jev-loop --scope user -- python $server
    Write-Host "MCP server registered: jev-loop -> $server (Claude Code)"
} else {
    Write-Host "claude not on PATH - skipping Claude Code MCP setup."
}

# Codex: skills live in ~/.agents/skills, the server in ~/.codex/config.toml.
if (Get-Command codex -ErrorAction SilentlyContinue) {
    $codexSkillDir = Join-Path $HOME ".agents\skills\jev-loop"
    New-Item -ItemType Directory -Force $codexSkillDir | Out-Null
    Copy-Item skill\jev-loop\* $codexSkillDir -Recurse -Force
    Write-Host "Skill installed: $codexSkillDir"

    codex mcp remove jev-loop 2>$null | Out-Null
    codex mcp add jev-loop -- python $server
    Write-Host "MCP server registered: jev-loop -> $server (Codex)"
} else {
    Write-Host "codex not on PATH - skipping Codex setup."
}

# Hermes: same server, same loop; the tools show up as mcp_jev_loop_*.
if (Get-Command hermes -ErrorAction SilentlyContinue) {
    $hermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $HOME ".hermes" }
    $hermesSkillDir = Join-Path $hermesHome "skills\jev-loop"
    New-Item -ItemType Directory -Force $hermesSkillDir | Out-Null
    Copy-Item skill\jev-loop\* $hermesSkillDir -Recurse -Force
    Write-Host "Skill installed: $hermesSkillDir"

    # A Hermes stdio MCP subprocess gets a filtered environment, so the key is handed over in
    # the server's env block - but ONLY when Hermes can resolve it: an unresolved
    # ${TYPESAFE_API_KEY} would reach Jev as the key itself instead of falling back to the key
    # file. Without the env block the server reads the key file on its own.
    $hermesEnvArgs = @()
    $hermesEnvFile = Join-Path $hermesHome ".env"
    if ((Test-Path $hermesEnvFile) -and (Select-String -Path $hermesEnvFile -Pattern '^TYPESAFE_API_KEY=.' -Quiet)) {
        $hermesEnvArgs = @("--env", 'TYPESAFE_API_KEY=${TYPESAFE_API_KEY}')
    }
    hermes mcp remove jev-loop 2>$null | Out-Null
    "y`n" | hermes mcp add jev-loop --command python @hermesEnvArgs --args $server
    Write-Host "MCP server registered: jev-loop -> $server (start a new Hermes session)"
} else {
    Write-Host "hermes not on PATH - skipping Hermes setup."
}

$keyFile = Join-Path $HOME ".config\jev-loop\typesafe_api_key"
if (-not [Environment]::GetEnvironmentVariable("TYPESAFE_API_KEY", "User") -and -not $env:TYPESAFE_API_KEY -and -not (Test-Path $keyFile)) {
    Write-Warning "No TypeSafe key. Set TYPESAFE_API_KEY (user env) or write it to $keyFile, then restart Claude Code."
} else {
    python $server --check
}
Write-Host "Done. Restart your harness (Claude Code / Codex), then say: 'byg med jev: <what you want>' or invoke the jev-loop skill (/jev-loop, or `$jev-loop in Codex)."
