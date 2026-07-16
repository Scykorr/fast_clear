@echo off
chcp 65001 >nul
:: Запуск fast_clear с повышением прав (UAC)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%~dp0venv\Scripts\python.exe' -ArgumentList '-m','fast_clear','--gui' -Verb RunAs -WorkingDirectory '%~dp0'"
