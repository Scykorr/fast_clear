"""Восстановление USB-клавиатуры/мыши после слишком агрессивной очистки Enum\\USB."""

from __future__ import annotations

import subprocess
from typing import Callable


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def repair_usb_input(progress: Callable[[str], None] | None = None) -> list[str]:
    """
    Переустанавливает проблемные HID/Keyboard/Mouse и пересканирует PnP.
    Безопасно вызывать от администратора.
    """
    log = progress or (lambda _m: None)
    notes: list[str] = []

    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$classes = @('Keyboard','Mouse','HIDClass','USB')

# 1) Включить устройства не в OK
Get-PnpDevice -Class $classes | Where-Object { $_.Status -ne 'OK' } | ForEach-Object {
  Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false
}

# 2) Удалить «фантомы» Unknown (Windows заново создаст при опросе шины)
Get-PnpDevice -Class Keyboard,Mouse,HIDClass | Where-Object { $_.Status -eq 'Unknown' } | ForEach-Object {
  try {
    & pnputil.exe /remove-device $_.InstanceId /force | Out-Null
  } catch {}
}

# 3) Перезапуск USB host / root hub
Get-PnpDevice -Class USB | Where-Object {
  $_.FriendlyName -match 'Root Hub|Host Controller|корнев|хост-контроллер|Корневой|Хост'
} | ForEach-Object {
  Disable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false
  Start-Sleep -Milliseconds 500
  Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false
}

# 4) Перескан
& pnputil.exe /scan-devices | Out-Null
Start-Sleep -Seconds 2

# Итог
$okK = @(Get-PnpDevice -Class Keyboard | Where-Object Status -eq 'OK').Count
$okM = @(Get-PnpDevice -Class Mouse | Where-Object Status -eq 'OK').Count
$bad = @(Get-PnpDevice -Class Keyboard,Mouse | Where-Object Status -ne 'OK').Count
Write-Output "OK_KEYBOARDS=$okK"
Write-Output "OK_MICE=$okM"
Write-Output "NOT_OK_INPUT=$bad"
"""
    log("Восстановление: удаление фантомов HID + перескан USB…")
    rc, out = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ]
    )
    for line in out.splitlines():
        line = line.strip()
        if line:
            notes.append(line)
            log(line)
    if rc != 0 and not notes:
        notes.append(f"powershell exit {rc}")
    notes.append(
        "Если USB-клавиатура/мышь всё ещё не работают: отключите и снова "
        "подключите кабель, либо перезагрузите ПК."
    )
    log(notes[-1])
    return notes
