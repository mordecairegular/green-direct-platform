param(
    [string]$Python = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m pip install pyinstaller
& $Python -m PyInstaller GreenDirectBatchTrial.spec --noconfirm --clean

Write-Host ""
Write-Host "Build completed: dist\GreenDirectBatchTrial\GreenDirectBatchTrial.exe"
