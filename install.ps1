# One-time setup for Claude Code: installs dependencies, copies the skill and
# registers the MCP server at user scope. Safe to run again after updates.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -q -r requirements.txt

$skillDir = Join-Path $HOME ".claude\skills\jev-loop"
New-Item -ItemType Directory -Force $skillDir | Out-Null
Copy-Item skill\jev-loop\SKILL.md $skillDir -Force
Write-Host "Skill installed: $skillDir"

$server = Join-Path $PSScriptRoot "jev_mcp.py"
claude mcp remove jev-loop --scope user 2>$null | Out-Null
claude mcp add jev-loop --scope user -- python $server
Write-Host "MCP server registered: jev-loop -> $server"

if (-not [Environment]::GetEnvironmentVariable("TYPESAFE_API_KEY", "User") -and -not $env:TYPESAFE_API_KEY) {
    Write-Warning "TYPESAFE_API_KEY is not set. Set it as a user environment variable, then restart Claude Code."
}
Write-Host "Done. Restart Claude Code, then say: 'byg med jev: <what you want>' or type /jev-loop."
