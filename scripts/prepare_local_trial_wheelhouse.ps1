param(
    [string]$WheelhouseDir = "",
    [switch]$Clean,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseRoot = Join-Path $RepoRoot "release"
if ([string]::IsNullOrWhiteSpace($WheelhouseDir)) {
    $WheelhouseDir = Join-Path $ReleaseRoot "wheelhouse"
}

function Assert-PathUnder {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    $prefix = $parentFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not ($pathFull.Equals($parentFull, [System.StringComparison]::OrdinalIgnoreCase) -or $pathFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing to operate outside expected directory: $pathFull"
    }
}

function Get-PythonCommand {
    $repoPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $repoPython -PathType Leaf) {
        return @($repoPython)
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @($py.Source, "-3")
    }
    throw "Python was not found. Install Python 3.10 or newer."
}

$requirements = Join-Path $RepoRoot "requirements-runtime.txt"
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Missing requirements-runtime.txt"
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Assert-PathUnder -Path $WheelhouseDir -Parent $ReleaseRoot
$pythonCommand = @(Get-PythonCommand)

if ($CheckOnly) {
    Write-Host "Wheelhouse check only:"
    Write-Host "  Python: $($pythonCommand -join ' ')"
    Write-Host "  Requirements: $requirements"
    Write-Host "  Wheelhouse: $([System.IO.Path]::GetFullPath($WheelhouseDir))"
    exit 0
}

if ($Clean -and (Test-Path -LiteralPath $WheelhouseDir)) {
    Remove-Item -LiteralPath $WheelhouseDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $WheelhouseDir | Out-Null

$pythonExe = $pythonCommand[0]
$pythonArgs = @()
if ($pythonCommand.Count -gt 1) {
    $pythonArgs = $pythonCommand[1..($pythonCommand.Count - 1)]
}

& $pythonExe @pythonArgs -m pip download -r $requirements -d $WheelhouseDir
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed with exit code $LASTEXITCODE"
}

$wheelCount = (Get-ChildItem -LiteralPath $WheelhouseDir -Filter "*.whl" -File).Count
$info = @(
    "Green Direct Local Trial Wheelhouse"
    "BuiltAt=$((Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz"))"
    "Python=$($pythonCommand -join ' ')"
    "Requirements=requirements-runtime.txt"
    "WheelCount=$wheelCount"
    "Note=Use scripts\build_local_trial_package.ps1 -IncludeWheelhouse to embed this wheelhouse in a local trial ZIP."
)
Set-Content -LiteralPath (Join-Path $WheelhouseDir "WHEELHOUSE_INFO.txt") -Value $info -Encoding UTF8

Write-Host "Built wheelhouse:"
Write-Host "  $([System.IO.Path]::GetFullPath($WheelhouseDir))"
Write-Host "  $wheelCount wheel files"
