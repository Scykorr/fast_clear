# Сборка fast_clear.exe (PyInstaller, onefile, GUI, UAC)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== fast_clear: сборка exe ===" -ForegroundColor Cyan

$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Не найден venv\Scripts\python.exe. Создайте: python -m venv venv"
}

Write-Host "[1/3] Установка PyInstaller..."
& $py -m pip install -q --upgrade pip pyinstaller

Write-Host "[2/3] Очистка build/ dist/..."
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist

Write-Host "[3/3] Сборка..."
& $py -m PyInstaller --noconfirm (Join-Path $PSScriptRoot "fast_clear.spec")

$exe = Join-Path $PSScriptRoot "dist\fast_clear.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Сборка не создала dist\fast_clear.exe"
}

Write-Host ""
Write-Host "Готово: $exe" -ForegroundColor Green
Get-Item $exe | Format-List Name, Length, LastWriteTime
