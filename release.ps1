# Cut a date-based release: version = yyyy.MM.dd.HHmm (local time).
# Moves "[Unreleased]" in CHANGELOG.md under the new version, writes VERSION,
# commits, tags v<version>, pushes and creates a GitHub release whose notes are
# that changelog section. Usage:  pwsh -File .\release.ps1  [-NoPush]
param([switch]$NoPush)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (git status --porcelain) { throw "Working tree is not clean. Commit or stash first." }

$version = Get-Date -Format "yyyy.MM.dd.HHmm"
if (git tag --list "v$version") { throw "Tag v$version already exists. Wait a minute and retry." }

# Validate everything before touching any file.
$log = Get-Content CHANGELOG.md -Raw -Encoding utf8
$m = [regex]::Match($log, "(?s)## \[Unreleased\]\s*(.*?)(?=\r?\n## \[|\z)")
if (-not $m.Success) { throw "CHANGELOG.md has no '## [Unreleased]' section." }
$notes = $m.Groups[1].Value.Trim()
if (-not $notes) { throw "The [Unreleased] section in CHANGELOG.md is empty. Describe the changes first." }

$date = Get-Date -Format "yyyy-MM-dd"
$log = $log.Substring(0, $m.Index) + "## [Unreleased]`n`n## [$version] - $date`n`n$notes`n" + $log.Substring($m.Index + $m.Length)
Set-Content -Path CHANGELOG.md -Value $log -NoNewline -Encoding utf8NoBOM
Set-Content -Path VERSION -Value $version -NoNewline -Encoding utf8NoBOM

git add VERSION CHANGELOG.md
git commit -m "Release $version"
git tag -a "v$version" -m "Release $version"
if (-not $NoPush) {
    git push
    git push origin "v$version"
    $notesFile = New-TemporaryFile
    Set-Content -Path $notesFile -Value $notes -Encoding utf8NoBOM
    gh release create "v$version" --title "v$version" --notes-file $notesFile
    Remove-Item $notesFile
}
Write-Host "Released $version"
