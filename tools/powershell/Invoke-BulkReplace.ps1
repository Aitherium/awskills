#Requires -Version 7.0
<#
.SYNOPSIS
    Find and replace text across multiple files matching a glob pattern.

.DESCRIPTION
    Recursively searches files under a directory, filters by glob, and
    performs a find/replace in each matching file. Supports plain-text and
    regex. Use -DryRun to preview without writing.

.PARAMETER Find
    Text or regex to search for.

.PARAMETER Replace
    Replacement text (supports $1, $2 backreferences when -Regex is used).

.PARAMETER Path
    Root directory to search in (default: current location).

.PARAMETER Filter
    File glob filter, e.g. "*.yaml" (default: all files).

.PARAMETER Regex
    Treat -Find as a regular expression.

.PARAMETER CaseSensitive
    Accepted for compatibility; matching is now case-sensitive by default.

.PARAMETER IgnoreCase
    Opt in to case-insensitive matching.

.PARAMETER DryRun
    Preview which files would be changed without writing.

.PARAMETER MaxFiles
    Maximum files to modify (safety limit, default: 50). If MORE files match,
    nothing is written and the script exits 1 (never a half-renamed tree).

.PARAMETER SelfTest
    Run the built-in regression test in a temp dir and exit 0 (pass) / 1 (fail).

.NOTES
    Plain mode (no -Regex) is literal on BOTH sides: '$' in -Replace is not
    expanded. Files containing NUL bytes (binaries) are skipped. Each file is
    written back in its own encoding (UTF-8 with/without BOM, UTF-16 LE/BE with
    BOM); files that are not valid UTF-8 and carry no BOM (e.g. Latin-1) are
    skipped and listed instead of being corrupted.

.EXAMPLE
    Invoke-BulkReplace -Find "oldName" -Replace "newName" -Filter "*.ts" -DryRun
    Preview changes to all TypeScript files.

.EXAMPLE
    Invoke-BulkReplace -Find "(\d{4})-(\d{2})-(\d{2})" -Replace "$3/$2/$1" -Regex -Path ./data
    Convert date format from YYYY-MM-DD to DD/MM/YYYY in ./data tree.
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Run')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Run')]
    [string]$Find,

    [Parameter(Mandatory, ParameterSetName = 'Run')]
    [AllowEmptyString()]
    [string]$Replace,

    [Parameter()]
    [string]$Path = (Get-Location).Path,

    [Parameter()]
    [string]$Filter = '*',

    [switch]$Regex,
    [switch]$CaseSensitive,
    [switch]$IgnoreCase,
    [switch]$DryRun,

    [Parameter()]
    [int]$MaxFiles = 50,

    [Parameter(ParameterSetName = 'SelfTest')]
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SelfTest) {
    $hostExe = (Get-Process -Id $PID).Path
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ibr-selftest-' + [guid]::NewGuid().ToString('N'))
    $fails = @()
    function Get-Hex([string]$p) { ([System.IO.File]::ReadAllBytes($p) | ForEach-Object { $_.ToString('x2') }) -join '' }
    try {
        $d1 = Join-Path $tmp 'mixed'; New-Item -ItemType Directory -Force -Path $d1 | Out-Null
        $png = Join-Path $d1 'img.png'
        [System.IO.File]::WriteAllBytes($png, [byte[]](0x89,0x50,0x4E,0x47,0x00,0x66,0x6F,0x6F,0xFF,0x00))
        $lat = Join-Path $d1 'latin1.txt'
        [System.IO.File]::WriteAllBytes($lat, [byte[]](0x63,0x61,0x66,0xE9,0x20,0x66,0x6F,0x6F,0x0A))
        $bom = Join-Path $d1 'bom.txt'
        [System.IO.File]::WriteAllBytes($bom, [byte[]]((0xEF,0xBB,0xBF) + [System.Text.Encoding]::ASCII.GetBytes("Foo foo`r`n")))
        $pngBefore = Get-Hex $png; $latBefore = Get-Hex $lat
        & $hostExe -NoProfile -File $PSCommandPath -Find 'foo' -Replace 'b$0r' -Path $d1 *> $null
        if ($LASTEXITCODE -ne 0) { $fails += "plain run exited $LASTEXITCODE" }
        if ((Get-Hex $png) -ne $pngBefore) { $fails += 'binary file (NUL bytes) was rewritten' }
        if ((Get-Hex $lat) -ne $latBefore) { $fails += 'Latin-1 file was rewritten (U+FFFD corruption)' }
        $want = 'efbbbf' + (([System.Text.Encoding]::ASCII.GetBytes("Foo b`$0r`r`n") | ForEach-Object { $_.ToString('x2') }) -join '')
        if ((Get-Hex $bom) -ne $want) { $fails += "BOM/CRLF/literal-`$/case-sensitive result wrong: $(Get-Hex $bom) != $want" }

        $d2 = Join-Path $tmp 'many'; New-Item -ItemType Directory -Force -Path $d2 | Out-Null
        foreach ($n in 'a', 'b', 'c') { [System.IO.File]::WriteAllText((Join-Path $d2 "$n.txt"), 'foo') }
        & $hostExe -NoProfile -File $PSCommandPath -Find 'foo' -Replace 'bar' -Path $d2 -MaxFiles 2 *> $null
        if ($LASTEXITCODE -eq 0) { $fails += 'over-MaxFiles run exited 0' }
        foreach ($n in 'a', 'b', 'c') {
            if ([System.IO.File]::ReadAllText((Join-Path $d2 "$n.txt")) -ne 'foo') { $fails += "over-MaxFiles run modified $n.txt (half-renamed tree)" }
        }

        $d3 = Join-Path $tmp 'ic'; New-Item -ItemType Directory -Force -Path $d3 | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $d3 'x.txt'), 'Foo')
        & $hostExe -NoProfile -File $PSCommandPath -Find 'foo' -Replace 'bar' -Path $d3 -IgnoreCase *> $null
        if ([System.IO.File]::ReadAllText((Join-Path $d3 'x.txt')) -ne 'bar') { $fails += '-IgnoreCase did not match Foo' }
    } finally {
        Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
    }
    if ($fails.Count -gt 0) { $fails | ForEach-Object { Write-Host "SELFTEST FAIL: $_" -ForegroundColor Red }; exit 1 }
    Write-Host 'SELFTEST PASS: binaries/Latin-1 untouched, BOM+CRLF kept, plain $ literal, case-sensitive default, MaxFiles refuses up front' -ForegroundColor Green
    exit 0
}

if ($CaseSensitive -and $IgnoreCase) {
    Write-Error '-CaseSensitive and -IgnoreCase are mutually exclusive.'
    exit 2
}

$root = Resolve-Path $Path -ErrorAction Stop
Write-Host "🔄 Bulk replace '$Find' → '$Replace' in $root ($Filter)" -ForegroundColor Cyan

$regexPattern = if ($Regex) { $Find } else { [regex]::Escape($Find) }
# Plain mode is literal on the replacement side too: '$' must not expand.
$replacement = if ($Regex) { $Replace } else { $Replace.Replace('$', '$$') }
$opts = if ($IgnoreCase) { [System.Text.RegularExpressions.RegexOptions]::IgnoreCase }
        else { [System.Text.RegularExpressions.RegexOptions]::None }

$files = Get-ChildItem -Path $root -Recurse -File -Filter $Filter -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '[\\/]\.' }

$modified = 0
$totalReplacements = 0
$skipped = @()
$candidates = @()
$strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)

# Pass 1: read and classify every file; write nothing yet.
foreach ($file in $files) {
    $rel = $file.FullName.Substring($root.Path.Length).TrimStart('\', '/')
    try {
        $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    } catch { $skipped += "$rel (unreadable)"; continue }

    $enc = $null; $bomLen = 0
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $enc = New-Object System.Text.UTF8Encoding($true, $true); $bomLen = 3
    } elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        $enc = New-Object System.Text.UnicodeEncoding($false, $true, $true); $bomLen = 2
    } elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        $enc = New-Object System.Text.UnicodeEncoding($true, $true, $true); $bomLen = 2
    } elseif ([Array]::IndexOf($bytes, [byte]0) -ge 0) {
        $skipped += "$rel (binary: contains NUL bytes)"; continue
    } else {
        $enc = $strictUtf8
    }
    try {
        $content = $enc.GetString($bytes, $bomLen, $bytes.Length - $bomLen)
    } catch {
        $skipped += "$rel (not valid UTF-8; left untouched)"; continue
    }

    $found = [regex]::Matches($content, $regexPattern, $opts)
    if ($found.Count -eq 0) { continue }
    $candidates += [PSCustomObject]@{ File = $file; Rel = $rel; Content = $content; Encoding = $enc; Count = $found.Count }
}

foreach ($s in $skipped) { Write-Host "  [SKIP] $s" -ForegroundColor DarkYellow }

if ($candidates.Count -gt $MaxFiles) {
    Write-Host "❌ $($candidates.Count) files match, more than -MaxFiles $MaxFiles. Nothing was changed; narrow -Path/-Filter or raise -MaxFiles." -ForegroundColor Red
    exit 1
}

# Pass 2: write each file back in its own encoding (BOM kept, newlines untouched).
foreach ($c in $candidates) {
    $count = $c.Count
    if ($DryRun) {
        Write-Host "  [DRY] $($c.Rel) — $count replacement(s)" -ForegroundColor Yellow
    } else {
        if ($PSCmdlet.ShouldProcess($c.File.FullName, "Replace $count occurrence(s)")) {
            $newContent = [regex]::Replace($c.Content, $regexPattern, $replacement, $opts)
            $out = [byte[]]($c.Encoding.GetPreamble() + $c.Encoding.GetBytes($newContent))
            [System.IO.File]::WriteAllBytes($c.File.FullName, $out)
            Write-Host "  ✏️  $($c.Rel) — $count replacement(s)" -ForegroundColor Green
        }
    }

    $modified++
    $totalReplacements += $count
}

$verb = if ($DryRun) { 'Would replace' } else { 'Replaced' }
Write-Host "`n✅ $verb $totalReplacements occurrence(s) across $modified file(s)." -ForegroundColor Green
