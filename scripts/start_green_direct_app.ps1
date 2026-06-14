[CmdletBinding()]
param(
    [int]$Port = 8503,
    [int]$MaxPort = 8515,
    [string]$ProjectRootOverride = "",
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[GreenDirect] $Message" -ForegroundColor Cyan
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[GreenDirect] $Message" -ForegroundColor Yellow
}

if ($ProjectRootOverride) {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRootOverride).Path
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}

$SrcRoot = Join-Path $ProjectRoot "src"
$AppPath = Join-Path $SrcRoot "green_direct\ui\app.py"
$RuntimeRoot = Join-Path $ProjectRoot ".runtime"
$RuntimeTemp = Join-Path $RuntimeRoot "tmp"

if (-not (Test-Path -LiteralPath $AppPath)) {
    throw "Streamlit app not found: $AppPath"
}

New-Item -ItemType Directory -Force -Path $RuntimeTemp | Out-Null

function Get-GreenDirectBrowserPath {
    $candidates = @()
    if (${env:ProgramFiles}) {
        $candidates += (Join-Path ${env:ProgramFiles} "Google\Chrome\Application\chrome.exe")
        $candidates += (Join-Path ${env:ProgramFiles} "Microsoft\Edge\Application\msedge.exe")
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe")
    }
    if (${env:LOCALAPPDATA}) {
        $candidates += (Join-Path ${env:LOCALAPPDATA} "Google\Chrome\Application\chrome.exe")
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
}

function Get-GreenDirectPython {
    $candidates = @(
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".runtime\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".python\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw "Python was not found. Install Python or create .venv with requirements.txt."
}

function Get-ProcessInfoById {
    param([int]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-GreenDirectStreamlitProcess {
    param($ProcessInfo)

    if ($null -eq $ProcessInfo -or [string]::IsNullOrWhiteSpace($ProcessInfo.CommandLine)) {
        return $false
    }

    $commandLine = $ProcessInfo.CommandLine.ToLowerInvariant().Replace("/", "\")
    $rootNeedle = $ProjectRoot.ToLowerInvariant().Replace("/", "\")
    $appNeedle = $AppPath.ToLowerInvariant().Replace("/", "\")

    return (
        $commandLine.Contains("streamlit") -and (
            $commandLine.Contains($appNeedle) -or
            $commandLine.Contains("src\green_direct\ui\app.py") -or
            $commandLine.Contains($rootNeedle)
        )
    )
}

function Get-GreenDirectStreamlitProcesses {
    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { Test-GreenDirectStreamlitProcess $_ }
    )
}

function Stop-GreenDirectStreamlitProcesses {
    $processes = @(Get-GreenDirectStreamlitProcesses)
    foreach ($processInfo in $processes) {
        Write-Warn "Stopping stale Green Direct Streamlit process PID $($processInfo.ProcessId)."
        Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if ($processes.Count -gt 0) {
        Start-Sleep -Seconds 1
    }
}

function Get-PortOwners {
    param([int]$CandidatePort)

    return @(
        Get-NetTCPConnection -LocalPort $CandidatePort -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Select-GreenDirectPort {
    param([switch]$AssumeGreenDirectStopped)

    for ($candidate = $Port; $candidate -le $MaxPort; $candidate++) {
        $owners = @(Get-PortOwners -CandidatePort $candidate)
        if ($owners.Count -eq 0) {
            return $candidate
        }

        if ($AssumeGreenDirectStopped) {
            $ownersAfterExpectedStop = @()
            foreach ($owner in $owners) {
                $processInfo = Get-ProcessInfoById -ProcessId $owner
                if (-not (Test-GreenDirectStreamlitProcess $processInfo)) {
                    $ownersAfterExpectedStop += $owner
                }
            }
            if ($ownersAfterExpectedStop.Count -eq 0) {
                return $candidate
            }
            $owners = $ownersAfterExpectedStop
        }

        $ownerLabels = @()
        foreach ($owner in $owners) {
            $processInfo = Get-ProcessInfoById -ProcessId $owner
            if ($processInfo) {
                $ownerLabels += "$owner/$($processInfo.Name)"
            } else {
                $ownerLabels += "$owner/unknown"
            }
        }
        Write-Warn "Port $candidate is already in use by $($ownerLabels -join ', '); trying the next port."
    }

    throw "No available localhost port found in $Port-$MaxPort."
}

$PythonExe = Get-GreenDirectPython
$OriginalPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($OriginalPythonPath)) {
    $env:PYTHONPATH = $SrcRoot
} else {
    $env:PYTHONPATH = "$SrcRoot;$OriginalPythonPath"
}
$env:TEMP = $RuntimeTemp
$env:TMP = $RuntimeTemp
$env:TMPDIR = $RuntimeTemp
if ([string]::IsNullOrWhiteSpace($env:GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT)) {
    $env:GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT = "1"
}
if ([string]::IsNullOrWhiteSpace($env:BROWSER_PATH)) {
    $BrowserPath = Get-GreenDirectBrowserPath
    if (-not [string]::IsNullOrWhiteSpace($BrowserPath)) {
        $env:BROWSER_PATH = $BrowserPath
    }
}

Write-Info "Project: $ProjectRoot"
Write-Info "Python:  $PythonExe"
Write-Info "Temp:    $RuntimeTemp"
if (-not [string]::IsNullOrWhiteSpace($env:BROWSER_PATH)) {
    Write-Info "Browser: $env:BROWSER_PATH"
}

$probe = @"
from green_direct.visualization.export_charts import DOCX_A4_PORTRAIT_PROFILE
import streamlit
import green_direct.ui.app
print('import-ok')
"@

& $PythonExe -c $probe
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Import preflight failed. Try: python -m pip install -r requirements.txt"
    exit $LASTEXITCODE
}

$existing = @(Get-GreenDirectStreamlitProcesses)
if ($existing.Count -gt 0) {
    $ids = ($existing | ForEach-Object { $_.ProcessId }) -join ", "
    Write-Warn "Found stale Green Direct Streamlit process(es): $ids"
}

if (-not $CheckOnly) {
    Stop-GreenDirectStreamlitProcesses
}

$SelectedPort = Select-GreenDirectPort -AssumeGreenDirectStopped:$CheckOnly
$Url = "http://localhost:$SelectedPort"

if ($CheckOnly) {
    Write-Info "Selected URL would be: $Url"
    Write-Info "Check complete. No process was started or stopped."
    exit 0
}

Write-Info "URL: $Url"
Write-Info "Starting Streamlit. Keep this window open while using the app."

if (-not $NoBrowser) {
    $browserCommand = "Start-Sleep -Seconds 5; Start-Process '$Url'"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", $browserCommand) `
        -WindowStyle Hidden | Out-Null
}

$streamlitArgs = @(
    "-m",
    "streamlit",
    "run",
    $AppPath,
    "--server.address=localhost",
    "--server.port=$SelectedPort",
    "--server.headless=true",
    "--browser.gatherUsageStats=false"
)

& $PythonExe @streamlitArgs
$exitCode = $LASTEXITCODE
Write-Info "Streamlit stopped with exit code $exitCode."
exit $exitCode
