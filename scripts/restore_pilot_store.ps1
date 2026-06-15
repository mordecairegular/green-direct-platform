[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupZip,
    [string]$StoreDir = ".runtime\pilot_store"
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

$backupPath = Resolve-GreenDirectPath $BackupZip
$storePath = Resolve-GreenDirectPath $StoreDir

if (-not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
    throw "Backup ZIP does not exist: $backupPath"
}

if (Test-Path -LiteralPath $storePath) {
    $existingItems = @(Get-ChildItem -LiteralPath $storePath -Force)
    if ($existingItems.Count -gt 0) {
        throw "Restore target is not empty: $storePath. Choose a new directory or move the existing store first."
    }
} else {
    New-Item -ItemType Directory -Force -Path $storePath | Out-Null
}

Expand-Archive -LiteralPath $backupPath -DestinationPath $storePath

Write-Host "Pilot store restored:"
Write-Host "  Backup: $backupPath"
Write-Host "  Target: $storePath"
