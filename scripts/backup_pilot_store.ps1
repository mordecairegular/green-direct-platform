[CmdletBinding()]
param(
    [string]$StoreDir = ".runtime\pilot_store",
    [string]$BackupDir = ".runtime\backups",
    [string]$Label = ""
)

$ErrorActionPreference = "Stop"

function Resolve-GreenDirectPath {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }

    $projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    return [System.IO.Path]::GetFullPath((Join-Path $projectRoot $PathValue))
}

$storePath = Resolve-GreenDirectPath $StoreDir
$backupPath = Resolve-GreenDirectPath $BackupDir

if (-not (Test-Path -LiteralPath $storePath -PathType Container)) {
    throw "Pilot store directory does not exist: $storePath"
}

$items = @(Get-ChildItem -LiteralPath $storePath -Force)
if ($items.Count -eq 0) {
    throw "Pilot store directory is empty; refusing to create a misleading backup: $storePath"
}

New-Item -ItemType Directory -Force -Path $backupPath | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safeLabel = ($Label -replace "[^A-Za-z0-9._-]", "-").Trim("-")
$suffix = if ([string]::IsNullOrWhiteSpace($safeLabel)) { "" } else { "-$safeLabel" }
$destination = Join-Path $backupPath "green-direct-pilot-store-$timestamp$suffix.zip"

Compress-Archive -LiteralPath ($items | ForEach-Object { $_.FullName }) -DestinationPath $destination -CompressionLevel Optimal

Write-Host "Pilot store backup created:"
Write-Host "  Source:      $storePath"
Write-Host "  Destination: $destination"
