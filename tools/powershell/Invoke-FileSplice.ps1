#Requires -Version 7.0
<#
.SYNOPSIS
    Splice (replace) a range of lines in a target file with content from a source file or inline text.

.DESCRIPTION
    Performs a surgical line-range replacement on a text file.

    Modes:
      -SourceFile   : Replace target lines with the entire content of a source file
      -Content      : Replace target lines with the provided string
      -DeleteOnly   : Just remove the line range (no replacement)

    Exit Codes:
      0 - Success
      1 - Validation failure (missing file, bad range)
      2 - Execution error

.PARAMETER TargetFile
    Path to the file being modified (required).

.PARAMETER StartLine
    First line to replace (1-indexed, inclusive, required).

.PARAMETER EndLine
    Last line to replace (1-indexed, inclusive, required).

.PARAMETER SourceFile
    Path to a file whose content replaces the target range.

.PARAMETER Content
    Inline string content to splice in (alternative to -SourceFile).

.PARAMETER DeleteOnly
    Remove the line range without inserting replacement content.

.PARAMETER Encoding
    Encoding used to decode a target that has no BOM (default: UTF8). A file's
    own BOM (UTF-8, UTF-16 LE/BE) always wins. The file is written back with the
    same BOM presence, newline style (LF or CRLF) and trailing newline it had.

.PARAMETER SelfTest
    Run the built-in regression test in a temp dir and exit 0 (pass) / 1 (fail).

.PARAMETER DryRun
    Show what would happen without writing.

.PARAMETER PassThru
    Return the result object instead of writing host output.

.EXAMPLE
    Invoke-FileSplice -TargetFile worker.js -SourceFile patch.js -StartLine 104 -EndLine 284
    Replace lines 104-284 of worker.js with patch.js content.

.EXAMPLE
    Invoke-FileSplice -TargetFile config.yaml -StartLine 10 -EndLine 10 -Content "key: new_value"
    Replace a single line with inline content.

.EXAMPLE
    Invoke-FileSplice -TargetFile worker.js -SourceFile patch.js -StartLine 50 -EndLine 100 -DryRun
    Preview what would be changed.
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'FromFile')]
param(
    [Parameter(Mandatory, ParameterSetName = 'FromFile')]
    [Parameter(Mandatory, ParameterSetName = 'Inline')]
    [Parameter(Mandatory, ParameterSetName = 'Delete')]
    [string]$TargetFile,

    [Parameter(Mandatory, ParameterSetName = 'FromFile')]
    [Parameter(Mandatory, ParameterSetName = 'Inline')]
    [Parameter(Mandatory, ParameterSetName = 'Delete')]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$StartLine,

    [Parameter(Mandatory, ParameterSetName = 'FromFile')]
    [Parameter(Mandatory, ParameterSetName = 'Inline')]
    [Parameter(Mandatory, ParameterSetName = 'Delete')]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$EndLine,

    [Parameter(ParameterSetName = 'FromFile')]
    [string]$SourceFile,

    [Parameter(ParameterSetName = 'Inline')]
    [string]$Content,

    [Parameter(ParameterSetName = 'Delete')]
    [switch]$DeleteOnly,

    [string]$Encoding = 'UTF8',
    [switch]$DryRun,
    [switch]$PassThru,

    [Parameter(Mandatory, ParameterSetName = 'SelfTest')]
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($SelfTest) {
    $hostExe = (Get-Process -Id $PID).Path
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ifs-selftest-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $fails = @()
    try {
        $ascii = [System.Text.Encoding]::ASCII
        # Case 1: LF shebang script, no BOM, single-line -Content.
        $f1 = Join-Path $tmp 's.sh'
        [System.IO.File]::WriteAllBytes($f1, $ascii.GetBytes("#!/bin/bash`necho one`necho two`n"))
        & $hostExe -NoProfile -File $PSCommandPath -TargetFile $f1 -StartLine 2 -EndLine 2 -Content 'echo ONE' *> $null
        if ($LASTEXITCODE -ne 0) { $fails += "single-line -Content exited $LASTEXITCODE" }
        $got = [System.IO.File]::ReadAllBytes($f1)
        $want = $ascii.GetBytes("#!/bin/bash`necho ONE`necho two`n")
        if ([Convert]::ToBase64String($got) -ne [Convert]::ToBase64String($want)) {
            $fails += 'LF/no-BOM file was not preserved byte-for-byte (BOM or CRLF added?)'
        }
        # Case 2: CRLF + BOM file, no trailing newline, keeps all three.
        $f2 = Join-Path $tmp 'w.txt'
        [System.IO.File]::WriteAllBytes($f2, [byte[]]((0xEF, 0xBB, 0xBF) + $ascii.GetBytes("a`r`nb`r`nc")))
        & $hostExe -NoProfile -File $PSCommandPath -TargetFile $f2 -StartLine 2 -EndLine 2 -Content "B1`nB2" *> $null
        $got = [System.IO.File]::ReadAllBytes($f2)
        $want = [byte[]]((0xEF, 0xBB, 0xBF) + $ascii.GetBytes("a`r`nB1`r`nB2`r`nc"))
        if ([Convert]::ToBase64String($got) -ne [Convert]::ToBase64String($want)) {
            $fails += 'CRLF/BOM/no-trailing-newline file was not preserved'
        }
    } finally {
        Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
    }
    if ($fails.Count -gt 0) { $fails | ForEach-Object { Write-Host "SELFTEST FAIL: $_" -ForegroundColor Red }; exit 1 }
    Write-Host 'SELFTEST PASS: newline style, BOM presence and trailing newline preserved; single-line -Content works' -ForegroundColor Green
    exit 0
}

# Decode a file honouring its BOM; report what to write back.
function Read-SpliceText([string]$p) {
    $bytes = [System.IO.File]::ReadAllBytes($p)
    $bomLen = 0
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $enc = New-Object System.Text.UTF8Encoding($false); $bomLen = 3
    } elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        $enc = New-Object System.Text.UnicodeEncoding($false, $false); $bomLen = 2
    } elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        $enc = New-Object System.Text.UnicodeEncoding($true, $false); $bomLen = 2
    } elseif ($Encoding -eq 'UTF8') {
        $enc = New-Object System.Text.UTF8Encoding($false)
    } else {
        $enc = [System.Text.Encoding]::$Encoding
    }
    $text = $enc.GetString($bytes, $bomLen, $bytes.Length - $bomLen)
    $bom = if ($bomLen -gt 0) { [byte[]]$bytes[0..($bomLen - 1)] } else { [byte[]]@() }
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $trailing = $text.EndsWith("`n")
    $body = if ($trailing) { $text.Substring(0, $text.Length - $(if ($text.EndsWith("`r`n")) { 2 } else { 1 })) } else { $text }
    $lines = if ($text.Length -eq 0) { @() } else { @($body -split "`r?`n") }
    return [PSCustomObject]@{ Lines = $lines; Encoding = $enc; Bom = $bom; NewLine = $nl; Trailing = $trailing }
}

# ── Resolve paths ────────────────────────────────────────────────────────────
$TargetFile = (Resolve-Path -Path $TargetFile -ErrorAction Stop).Path

if ($PSCmdlet.ParameterSetName -eq 'FromFile') {
    if (-not $SourceFile) {
        Write-Error "Must provide -SourceFile, -Content, or -DeleteOnly"
        exit 1
    }
    $SourceFile = (Resolve-Path -Path $SourceFile -ErrorAction Stop).Path
}

# ── Validate ─────────────────────────────────────────────────────────────────
if (-not (Test-Path $TargetFile -PathType Leaf)) {
    Write-Error "Target file not found: $TargetFile"
    exit 1
}

if ($EndLine -lt $StartLine) {
    Write-Error "EndLine ($EndLine) must be >= StartLine ($StartLine)"
    exit 1
}

# ── Read target ──────────────────────────────────────────────────────────────
$targetText = Read-SpliceText $TargetFile
$lines = @($targetText.Lines)
$totalBefore = $lines.Count

if ($StartLine -gt $totalBefore) {
    Write-Error "StartLine ($StartLine) exceeds file length ($totalBefore lines)"
    exit 1
}

$effectiveEnd = [Math]::Min($EndLine, $totalBefore)
$linesRemoved = $effectiveEnd - $StartLine + 1

# ── Build new content ────────────────────────────────────────────────────────
switch ($PSCmdlet.ParameterSetName) {
    'FromFile' {
        if (-not (Test-Path $SourceFile -PathType Leaf)) {
            Write-Error "Source file not found: $SourceFile"
            exit 1
        }
        $newLines = @((Read-SpliceText $SourceFile).Lines)
    }
    'Inline' {
        $newLines = @($Content -split "`n" | ForEach-Object { $_.TrimEnd("`r") })
    }
    'Delete' {
        $newLines = @()
    }
}

$linesInserted = @($newLines).Count

# ── Splice ───────────────────────────────────────────────────────────────────
# prefix = lines[0 .. StartLine-2], suffix = lines[effectiveEnd .. end]
$prefix = if ($StartLine -gt 1) { $lines[0..($StartLine - 2)] } else { @() }
$suffix = if ($effectiveEnd -lt $totalBefore) { $lines[$effectiveEnd..($totalBefore - 1)] } else { @() }

$result = @()
$result += $prefix
$result += $newLines
$result += $suffix

$totalAfter = $result.Count

# ── Result object ────────────────────────────────────────────────────────────
$output = [PSCustomObject]@{
    TargetFile      = $TargetFile
    SourceFile      = if ($PSCmdlet.ParameterSetName -eq 'FromFile') { $SourceFile } else { $null }
    LinesRemoved    = $linesRemoved
    LinesInserted   = $linesInserted
    TotalBefore     = $totalBefore
    TotalAfter      = $totalAfter
    RangeReplaced   = "${StartLine}-${effectiveEnd}"
    DryRun          = [bool]$DryRun
}

# ── Write or preview ─────────────────────────────────────────────────────────
if ($DryRun) {
    Write-Host "╔═══ DRY RUN ═══════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "║ Target   : $TargetFile" -ForegroundColor Yellow
    if ($PSCmdlet.ParameterSetName -eq 'FromFile') {
        Write-Host "║ Source   : $SourceFile" -ForegroundColor Yellow
    }
    Write-Host "║ Range    : lines $StartLine – $effectiveEnd ($linesRemoved lines)" -ForegroundColor Yellow
    Write-Host "║ Inserting: $linesInserted lines" -ForegroundColor Yellow
    Write-Host "║ Before   : $totalBefore lines  →  After: $totalAfter lines" -ForegroundColor Yellow
    Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
}
else {
    if ($PSCmdlet.ShouldProcess($TargetFile, "Splice lines $StartLine-$effectiveEnd")) {
        $outText = [string]::Join($targetText.NewLine, [string[]]$result)
        if ($targetText.Trailing -and $result.Count -gt 0) { $outText += $targetText.NewLine }
        $outBytes = [byte[]]($targetText.Bom + $targetText.Encoding.GetBytes($outText))
        [System.IO.File]::WriteAllBytes($TargetFile, $outBytes)
        Write-Host "✓ Spliced $TargetFile : replaced lines $StartLine–$effectiveEnd ($linesRemoved → $linesInserted lines). Total: $totalBefore → $totalAfter" -ForegroundColor Green
    }
}

if ($PassThru) { $output }

exit 0
