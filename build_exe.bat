@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo === fast_clear: сборка exe ===
echo.

if not exist "venv\Scripts\python.exe" (
  echo [Ошибка] Не найден venv\Scripts\python.exe
  echo Создайте окружение: python -m venv venv
  exit /b 1
)

echo [1/3] Установка PyInstaller...
.\venv\Scripts\python.exe -m pip install -q --upgrade pip pyinstaller
if errorlevel 1 (
  echo [Ошибка] Не удалось установить PyInstaller
  exit /b 1
)

echo [2/3] Очистка старых артефактов build\ dist\ ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Сборка (onefile, GUI, UAC admin)...
.\venv\Scripts\python.exe -m PyInstaller --noconfirm fast_clear.spec
if errorlevel 1 (
  echo [Ошибка] Сборка не удалась
  exit /b 1
)

echo.
echo Готово: dist\fast_clear.exe
echo Запускайте на целевом ПК от имени администратора (UAC запросится сам).
echo.
dir /b dist\fast_clear.exe
exit /b 0
