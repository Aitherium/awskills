<#
.SYNOPSIS
    Recovers Docker Desktop from the WSL2 500-error hang without rebooting.
.DESCRIPTION
    When Docker Desktop's Linux engine wedges (API returns 500), this script:
    1. Kills Docker Desktop's own processes (never vmmem/wslservice, which
       host EVERY WSL distro on the machine)
    2. Terminates only Docker's WSL distros (docker-desktop, docker-desktop-data)
    3. Restarts the Docker Desktop Windows service (admin only; the WSL
       service is left alone)
    4. Starts Docker Desktop and, once healthy, restarts only exited containers
       whose restart policy is 'always' or 'unless-stopped'
    Dead containers are listed, and removed only with -RemoveDead.
    Can also run as a scheduled task to auto-detect and recover.
    Exits 2 without doing anything when the docker CLI is not installed.
.PARAMETER Monitor
    Run in monitoring loop — checks every 30s, auto-recovers on failure.
.PARAMETER Interval
    Seconds between health checks in monitor mode (default: 30).
.PARAMETER RemoveDead
    After recovery, `docker rm -f` containers in the 'dead' state. Without
    this switch they are only listed.
#>
param(
    [switch]$Monitor,
    [int]$Interval = 30,
    [switch]$RemoveDead
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-DockerHealthy {
    try {
        $result = docker info 2>&1
        if ($LASTEXITCODE -ne 0 -or $result -match '500 Internal Server Error') {
            return $false
        }
        return $true
    } catch {
        return $false
    }
}

function Invoke-DockerRecovery {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$timestamp] Docker engine is DOWN. Starting recovery..." -ForegroundColor Red

    # Phase 1: Kill Docker Desktop UI processes
    Write-Host "  [1/5] Killing Docker Desktop processes..." -ForegroundColor Yellow
    Stop-Process -Name 'Docker Desktop' -Force -ErrorAction SilentlyContinue
    Stop-Process -Name 'com.docker.backend' -Force -ErrorAction SilentlyContinue
    Stop-Process -Name 'com.docker.build' -Force -ErrorAction SilentlyContinue
    Stop-Process -Name 'docker-agent' -Force -ErrorAction SilentlyContinue
    Stop-Process -Name 'docker-sandbox' -Force -ErrorAction SilentlyContinue
    Start-Sleep 2

    # Phase 2: Shut down WSL (kills the hung Linux VM)
    Write-Host "  [2/5] Shutting down WSL..." -ForegroundColor Yellow
    # NOT `wsl --shutdown`: that is GLOBAL and stops EVERY WSL distro on the
    # machine, including ones unrelated to Docker that may be running real
    # workloads. Docker only needs its own distros to release their VHDX locks.
    foreach ($d in 'docker-desktop','docker-desktop-data') { wsl --terminate $d 2>$null }
    Start-Sleep 3

    # Phase 3: Sweep leftover Docker Desktop processes ONLY.
    # NOT vmmem / wslservice.exe: those are the shared WSL utility VM and service
    # behind EVERY distro, so killing them is the same global outage as
    # `wsl --shutdown` (see Phase 2).
    Write-Host "  [3/5] Cleaning up leftover Docker Desktop processes..." -ForegroundColor Yellow
    Get-Process -Name 'com.docker.*', 'Docker Desktop', 'vpnkit*' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 2

    # Phase 4: Stop and restart Windows services (needs admin)
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        Write-Host "  [4/5] Restarting Docker Windows service..." -ForegroundColor Yellow
        Stop-Service 'com.docker.service' -Force -ErrorAction SilentlyContinue
        # wslservice is deliberately NOT stopped: it serves every WSL distro.
        Start-Sleep 2
        Start-Service 'com.docker.service' -ErrorAction SilentlyContinue
    } else {
        Write-Host "  [4/5] Skipping service restart (not admin). If this doesn't work, run as admin." -ForegroundColor DarkYellow
    }
    Start-Sleep 2

    # Phase 5: Restart Docker Desktop
    Write-Host "  [5/5] Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

    # Wait for engine to come back
    Write-Host "  Waiting for Docker engine..." -ForegroundColor Cyan
    $maxWait = 90
    $waited = 0
    while ($waited -lt $maxWait) {
        Start-Sleep 5
        $waited += 5
        if (Test-DockerHealthy) {
            $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
            Write-Host "[$timestamp] Docker recovered in ${waited}s!" -ForegroundColor Green

            # Dead containers: list them; remove only on explicit -RemoveDead.
            $dead = @(docker ps -a --filter "status=dead" --format "{{.Names}}" 2>$null)
            if ($dead.Count -gt 0) {
                if ($RemoveDead) {
                    Write-Host "  Removing dead containers (-RemoveDead): $($dead -join ', ')" -ForegroundColor Yellow
                    foreach ($c in $dead) {
                        docker rm -f $c 2>$null
                    }
                } else {
                    Write-Host "  Dead containers (left in place; re-run with -RemoveDead to remove): $($dead -join ', ')" -ForegroundColor DarkYellow
                }
            }

            # Restart ONLY exited containers whose restart policy asks for it.
            # An exited container with policy 'no'/'on-failure' was stopped on purpose.
            $exited = @(docker ps -a --filter "status=exited" --format "{{.Names}}" 2>$null)
            foreach ($c in $exited) {
                $policy = docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' $c 2>$null
                if ($LASTEXITCODE -eq 0 -and "$policy".Trim() -in @('always', 'unless-stopped')) {
                    Write-Host "  Restarting $c (restart policy: $("$policy".Trim()))" -ForegroundColor Yellow
                    docker start $c 2>$null | Out-Null
                }
            }

            return $true
        }
        Write-Host "  ... ${waited}s elapsed" -ForegroundColor DarkGray
    }

    Write-Host "[$timestamp] Recovery FAILED after ${maxWait}s. You may need to reboot." -ForegroundColor Red
    return $false
}

# --- Main ---

# Without a docker CLI, Test-DockerHealthy can only ever say "unhealthy", and a
# no-arg run would go straight into killing processes and services.
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "docker CLI not found on PATH - cannot judge engine health; doing nothing." -ForegroundColor Red
    exit 2
}

if ($Monitor) {
    Write-Host "Docker health monitor started (checking every ${Interval}s). Ctrl+C to stop." -ForegroundColor Cyan
    while ($true) {
        if (-not (Test-DockerHealthy)) {
            Invoke-DockerRecovery
        }
        Start-Sleep $Interval
    }
} else {
    if (Test-DockerHealthy) {
        Write-Host "Docker engine is healthy. Nothing to do." -ForegroundColor Green
        docker ps --format "table {{.Names}}`t{{.Status}}" | Select-Object -First 20
    } else {
        Invoke-DockerRecovery
    }
}
