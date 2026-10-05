#Requires -Version 7.0
<#
.SYNOPSIS
    Creates a new Git branch from the current or specified base branch.

.DESCRIPTION
    Creates and switches to a new branch following conventional branch naming
    conventions (feature/*, fix/*, chore/*, etc.). Auto-prefixes if not provided.

.PARAMETER Name
    Branch name. If it doesn't include a prefix (feature/, fix/, chore/,
    hotfix/, release/, experiment/), 'feature/' will be prepended automatically.

.PARAMETER Base
    Base branch to create from. Defaults to 'develop'.

.PARAMETER NoSwitch
    Create the branch but don't switch to it.

.PARAMETER Prefixes
    Custom list of allowed branch prefixes (default: feature, fix, chore, hotfix, release, experiment).

.PARAMETER SelfTest
    Run the built-in regression test in a throwaway temp repo and exit 0/1.

    Exit codes: 0 branch created; 1 git fetch/branch/checkout failed (its output
    is printed, no check mark).

.EXAMPLE
    New-GitBranch -Name "add-auth-service"
    Creates feature/add-auth-service from develop.

.EXAMPLE
    New-GitBranch -Name "fix/broken-deploy" -Base main
    Creates fix/broken-deploy from main and switches to it.

.EXAMPLE
    New-GitBranch -Name "hotfix/critical-bug" -NoSwitch
    Creates hotfix/critical-bug but stays on current branch.
#>
[CmdletBinding(DefaultParameterSetName = 'Run')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Run')]
    [string]$Name,

    [Parameter()]
    [string]$Base = 'develop',

    [switch]$NoSwitch,

    [Parameter()]
    [string[]]$Prefixes = @('feature', 'fix', 'chore', 'hotfix', 'release', 'experiment'),

    [Parameter(Mandatory, ParameterSetName = 'SelfTest')]
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'

if ($SelfTest) {
    $hostExe = (Get-Process -Id $PID).Path
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ngb-selftest-' + [guid]::NewGuid().ToString('N'))
    $fails = @()
    try {
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        git -C $tmp init -q 2>&1 | Out-Null
        git -C $tmp config user.email selftest@example.invalid
        git -C $tmp config user.name selftest
        git -C $tmp config core.hooksPath (Join-Path $tmp 'no-hooks')
        Set-Content -Path (Join-Path $tmp 'a') -Value '1'
        git -C $tmp add a 2>&1 | Out-Null
        git -C $tmp commit -q -m init 2>&1 | Out-Null
        # No 'origin' remote: fetch and checkout must fail, and the script must say so.
        foreach ($extra in @(@(), @('-NoSwitch'))) {
            Push-Location $tmp
            try { & $hostExe -NoProfile -File $PSCommandPath -Name 'selftest-branch' @extra *> $null; $code = $LASTEXITCODE } finally { Pop-Location }
            if ($code -eq 0) { $fails += "run with no origin remote exited 0 ($($extra -join ' '))" }
        }
        if (@(git -C $tmp branch --list 'feature/selftest-branch').Count -gt 0) { $fails += 'branch was created despite the failure' }
    } finally {
        Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
    }
    if ($fails.Count -gt 0) { $fails | ForEach-Object { Write-Host "SELFTEST FAIL: $_" -ForegroundColor Red }; exit 1 }
    Write-Host 'SELFTEST PASS: fetch/checkout failures exit 1 with no check mark' -ForegroundColor Green
    exit 0
}

# Run git; on failure print its output and exit 1 (never a false check mark).
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

# Auto-prefix if no convention prefix present
$hasPrefix = $false
foreach ($p in $Prefixes) {
    if ($Name.StartsWith("$p/")) {
        $hasPrefix = $true
        break
    }
}
if (-not $hasPrefix) {
    $Name = "feature/$Name"
    Write-Host "  Auto-prefixed branch name: $Name" -ForegroundColor DarkGray
}

# Sanitize branch name
$Name = $Name -replace '[^a-zA-Z0-9/_-]', '-' -replace '-+', '-'

# Ensure we're on the base branch and up to date
Write-Host "  Creating branch '$Name' from '$Base'..." -ForegroundColor Cyan

Invoke-GitChecked fetch origin $Base | Out-Null

if ($NoSwitch) {
    Invoke-GitChecked branch $Name "origin/$Base" | Out-Null
    Write-Host "  ✓ Branch '$Name' created (not switched)" -ForegroundColor Green
} else {
    Invoke-GitChecked checkout -b $Name "origin/$Base" | Out-Null
    Write-Host "  ✓ Switched to new branch '$Name'" -ForegroundColor Green
}

# Show current state
git log --oneline -3
