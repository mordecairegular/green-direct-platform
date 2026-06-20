param(
    [string]$PackageDate = (Get-Date -Format "yyyyMMdd"),
    [switch]$IncludeWheelhouse,
    [string]$WheelhouseDir = "",
    [switch]$KeepExpanded
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseRoot = Join-Path $RepoRoot "release"
$PackageName = "GreenDirectLocalTrial_$PackageDate"
$PackageDir = Join-Path $ReleaseRoot $PackageName
$ZipPath = "$PackageDir.zip"

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

function Copy-RequiredFile {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [string]$DestinationRelativePath = $RelativePath
    )

    $source = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required file not found: $RelativePath"
    }
    $destination = Join-Path $PackageDir $DestinationRelativePath
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Copy-RequiredDirectory {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $source = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required directory not found: $RelativePath"
    }
    $destination = Join-Path $PackageDir $RelativePath
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Assert-PathUnder -Path $PackageDir -Parent $ReleaseRoot
Assert-PathUnder -Path $ZipPath -Parent $ReleaseRoot

if (Test-Path -LiteralPath $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

Copy-RequiredFile "START_GREEN_DIRECT_LOCAL_TRIAL.bat"
Copy-RequiredFile "START_GREEN_DIRECT_APP.bat"
Copy-RequiredFile "LOCAL_TRIAL_README.md"
Copy-RequiredFile "README.md"
Copy-RequiredFile "requirements-runtime.txt"
Copy-RequiredFile "requirements.txt"
Copy-RequiredFile "pyproject.toml"
Copy-RequiredFile "docs\USER_QUICK_GUIDE.md"
Copy-RequiredFile "docs\LOCAL_TRIAL_DISTRIBUTION.md"
Copy-RequiredFile "scripts\start_green_direct_app.ps1"

Copy-RequiredDirectory "src"
Copy-RequiredDirectory "config"
Copy-RequiredDirectory "samples"

if ($IncludeWheelhouse) {
    if ([string]::IsNullOrWhiteSpace($WheelhouseDir)) {
        $WheelhouseDir = Join-Path $ReleaseRoot "wheelhouse"
    }
    Assert-PathUnder -Path $WheelhouseDir -Parent $ReleaseRoot
    $resolvedWheelhouse = (Resolve-Path -LiteralPath $WheelhouseDir -ErrorAction Stop).Path
    $wheelFiles = Get-ChildItem -LiteralPath $resolvedWheelhouse -Filter "*.whl" -File -ErrorAction Stop
    if ($wheelFiles.Count -eq 0) {
        throw "Wheelhouse directory has no .whl files: $resolvedWheelhouse"
    }
    Copy-Item -LiteralPath $resolvedWheelhouse -Destination (Join-Path $PackageDir "wheelhouse") -Recurse -Force
}

$gitCommit = ""
$gitStatus = ""
try {
    $gitCommit = (& git -C $RepoRoot rev-parse --short HEAD 2>$null).Trim()
    $gitStatus = (& git -C $RepoRoot status --short --branch 2>$null) -join [Environment]::NewLine
} catch {
    $gitCommit = "unknown"
    $gitStatus = "git status unavailable"
}

$buildInfo = @(
    "Green Direct Local Trial Package"
    "BuiltAt=$((Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz"))"
    "GitCommit=$gitCommit"
    "PackageName=$PackageName"
    "IncludeWheelhouse=$IncludeWheelhouse"
    ""
    "GitStatus:"
    $gitStatus
)
Set-Content -LiteralPath (Join-Path $PackageDir "BUILD_INFO.txt") -Value $buildInfo -Encoding UTF8

Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force

if (-not $KeepExpanded) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}

$zipItem = Get-Item -LiteralPath $ZipPath
Write-Host "Built local trial package:"
Write-Host "  $($zipItem.FullName)"
Write-Host "  $([Math]::Round($zipItem.Length / 1MB, 2)) MB"
