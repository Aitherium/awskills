#Requires -Version 7.0
<#
.SYNOPSIS
    Stages and commits changes with a conventional commit message.

.DESCRIPTION
    Stages specified files (or all changes) and creates a commit following
    the Conventional Commits format (https://www.conventionalcommits.org/).

    Allowed commit types: feat, fix, chore, docs, refactor, test, ci, perf, build, style, revert

.PARAMETER Message
    Commit message. Should follow conventional format: type(scope): description
    Example: feat(auth): add OAuth2 login

.PARAMETER Files
    Specific files/patterns to stage. If omitted, stages only changes to files
    git already tracks (git add -u); untracked files such as .env are NOT staged.

.PARAMETER Push
    Push to remote after committing.

.PARAMETER Remote
    Remote to push to. Default: origin

.PARAMETER Branch
    Branch to push. If omitted, uses current branch.

.PARAMETER SelfTest
    Run the built-in regression test in throwaway temp repos and exit 0/1.

    Exit codes: 0 committed (and pushed); 1 any git step failed (the failing
    command's output is printed, no success line).

.EXAMPLE
    New-GitCommit -Message "feat(api): add user endpoints"
    Stage tracked changes and commit with conventional message.

.EXAMPLE
    New-GitCommit -Message "fix: typo in README" -Files "README.md" -Push
    Commit specific file and push to origin.
#>
[CmdletBinding(DefaultParameterSetName = 'Run')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Run')]
    [string]$Message,

    [Parameter()]
    [string]$Files,

    [switch]$Push,

    [string]$Remote = 'origin',

    [string]$Branch,

    [Parameter(Mandatory, ParameterSetName = 'SelfTest')]
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'

if ($SelfTest) {
    $hostExe = (Get-Process -Id $PID).Path
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ngc-selftest-' + [guid]::NewGuid().ToString('N'))
    $fails = @()
    function New-TestRepo([string]$dir, [string]$hookBody) {
        New-Item -ItemType Directory -Force -Path (Join-Path $dir 'hk') | Out-Null
        git -C $dir init -q 2>&1 | Out-Null
        git -C $dir config user.email selftest@example.invalid
        git -C $dir config user.name selftest
        git -C $dir config core.hooksPath (Join-Path $dir 'hk')
        Set-Content -Path (Join-Path $dir 'a') -Value '1'
        git -C $dir add a 2>&1 | Out-Null
        git -C $dir commit -q -m init 2>&1 | Out-Null
        if ($hookBody) {
            $hk = Join-Path $dir 'hk/pre-commit'
            [System.IO.File]::WriteAllText($hk, $hookBody)
            # git silently SKIPS a non-executable hook on Linux/macOS, and the commit succeeds
            if (-not $IsWindows) { chmod +x $hk }
        }
        Set-Content -Path (Join-Path $dir 'a') -Value '2'
        Set-Content -Path (Join-Path $dir '.env') -Value 'SECRET=x'
    }
    try {
        # Case 1: a pre-commit hook rejects the commit -> non-zero exit; .env never staged.
        $r1 = Join-Path $tmp 'r1'
        New-TestRepo $r1 "#!/bin/sh`necho REJECTED >&2`nexit 1`n"
        Push-Location $r1
        try { & $hostExe -NoProfile -File $PSCommandPath -Message 'fix: x' *> $null; $code = $LASTEXITCODE } finally { Pop-Location }
        if ($code -eq 0) { $fails += 'rejected commit exited 0' }
        $staged = @(git -C $r1 diff --cached --name-only)
        if ($staged -contains '.env') { $fails += 'untracked .env was staged without -Files' }
        # Case 2: commit succeeds, push to a missing remote fails -> non-zero exit.
        $r2 = Join-Path $tmp 'r2'
        New-TestRepo $r2 $null
        Push-Location $r2
        try { & $hostExe -NoProfile -File $PSCommandPath -Message 'fix: y' -Push -Remote 'no-such-remote' *> $null; $code = $LASTEXITCODE } finally { Pop-Location }
        if ($code -eq 0) { $fails += 'failed push exited 0' }
    } finally {
        Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
    }
    if ($fails.Count -gt 0) { $fails | ForEach-Object { Write-Host "SELFTEST FAIL: $_" -ForegroundColor Red }; exit 1 }
    Write-Host 'SELFTEST PASS: failed commit/push exit non-zero; no-Files mode stages tracked changes only' -ForegroundColor Green
    exit 0
}

# Run git; on failure print its output and exit 1 (never a false success line).
function Invoke-GitChecked {
    # Local 'Continue': under 'Stop', Windows PowerShell 5.1 turns redirected
    # native stderr into a terminating error before the exit code is checked.
    $ErrorActionPreference = 'Continue'
    $out = & git @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ git $($args -join ' ') failed (exit $LASTEXITCODE)" -ForegroundColor Red
        $out | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        exit 1
    }
    return $out
}

# Validate conventional commit format (advisory)
$conventionalPattern = '^(feat|fix|chore|docs|refactor|test|ci|perf|build|style|revert)(\(.+\))?(!)?:\s.+'
if ($Message -notmatch $conventionalPattern) {
    Write-Host "  ⚠ Message doesn't follow conventional commits format" -ForegroundColor Yellow
    Write-Host "    Expected: type(scope): description" -ForegroundColor DarkGray
    Write-Host "    Example:  feat(deploy): add ring promotion" -ForegroundColor DarkGray
}

# Stage files
if ($Files) {
    $fileList = $Files -split '[,;]' | ForEach-Object { $_.Trim() }
    foreach ($f in $fileList) {
        Invoke-GitChecked add -- $f | Out-Null
    }
    Write-Host "  Staged $(@($fileList).Count) path(s)" -ForegroundColor Gray
} else {
    Invoke-GitChecked add -u | Out-Null
    Write-Host "  Staged changes to TRACKED files only (git add -u); untracked files were not added - pass -Files to include them" -ForegroundColor Gray
}

# Check for changes
$staged = Invoke-GitChecked diff --cached --stat
if (-not $staged) {
    Write-Host "  ℹ Nothing to commit (working tree clean)" -ForegroundColor Yellow
    exit 0
}

Write-Host "  Changes to commit:" -ForegroundColor Cyan
$staged | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

# Commit
Invoke-GitChecked commit -m $Message | Out-Null
$commitHash = Invoke-GitChecked rev-parse --short HEAD
Write-Host "  ✓ Committed: $commitHash $Message" -ForegroundColor Green

# Push if requested
if ($Push) {
    if (-not $Branch) {
        $Branch = Invoke-GitChecked symbolic-ref --short HEAD
    }
    Write-Host "  Pushing to $Remote/$Branch..." -ForegroundColor Cyan
    Invoke-GitChecked push $Remote $Branch | Out-Null
    Write-Host "  ✓ Pushed to $Remote/$Branch" -ForegroundColor Green
}
exit 0
