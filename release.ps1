# Cut a date-based release: version = yyyy.MM.dd.HHmm (local time).
# Writes VERSION, moves "Unreleased" in CHANGELOG.md under the new version,
# commits, tags v<version> and pushes. Usage:  .\release.ps1  [-NoPush]
param([switch]$NoPush)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (git status --porcelain) { throw "Working tree is not clean. Commit or stash first." }

$version = Get-Date -Format "yyyy.MM.dd.HHmm"
if (git tag --list "v$version") { throw "Tag v$version already exists. Wait a minute and retry." }

Set-Content -Path VERSION -Value $version -NoNewline -Encoding utf8NoBOM

$date = Get-Date -Format "yyyy-MM-dd"
$log = Get-Content CHANGELOG.md -Raw -Encoding utf8
if ($log -notmatch "## \[Unreleased\]") { throw "CHANGELOG.md has no '## [Unreleased]' section." }
$log = $log -replace "## \[Unreleased\]", "## [Unreleased]`n`n## [$version] - $date"
Set-Content -Path CHANGELOG.md -Value $log -NoNewline -Encoding utf8NoBOM

git add VERSION CHANGELOG.md
git commit -m "Release $version"
git tag -a "v$version" -m "Release $version"
if (-not $NoPush) {
    git push
    git push origin "v$version"
    gh release create "v$version" --title "v$version" --notes "Se CHANGELOG.md for detaljer."
}
Write-Host "Released $version"
