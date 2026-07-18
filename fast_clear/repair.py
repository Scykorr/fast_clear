"""Восстановление работы USB после агрессивной очистки.

Чинит два класса проблем:
- USB-клавиатура/мышь/HID не определяются (фантомы, отключённые устройства);
- USB-флешки/накопители не подключаются (битые phantom-ноды, мусорные точки
  монтирования, изменённое владение веток Enum).
"""

from __future__ import annotations

import subprocess
from typing import Callable


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def _powershell(script: str, timeout: int = 180) -> tuple[int, str]:
    return _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )


_REPAIR_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'

# 1) Восстановить владельца веток Enum (SYSTEM), чтобы PnP мог создавать устройства
$adminEnum = @(
  'HKLM:\SYSTEM\CurrentControlSet\Enum\USB',
  'HKLM:\SYSTEM\CurrentControlSet\Enum\USBSTOR'
)
# (owner-reset делается в Python через WinAPI; здесь — PnP-часть)

# 2) Включить устройства не в статусе OK
$classes = @('Keyboard','Mouse','HIDClass','USB','DiskDrive','WPD')
Get-PnpDevice -Class $classes | Where-Object { $_.Status -ne 'OK' -and $_.Status -ne 'Unknown' } | ForEach-Object {
  Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false
}

# 3) Удалить phantom-ноды (Unknown) для ввода и накопителей — Windows создаст заново
Get-PnpDevice | Where-Object { $_.Status -eq 'Unknown' -and (
    $_.InstanceId -match '^USBSTOR\\' -or
    $_.InstanceId -match '^USB\\VID_' -or
    $_.InstanceId -match '^STORAGE\\Volume' -or
    $_.InstanceId -match '^SWD\\WPDBUSENUM' -or
    $_.Class -in @('Keyboard','Mouse','HIDClass','DiskDrive','WPD')
) } | ForEach-Object {
  & pnputil.exe /remove-device $_.InstanceId 2>$null | Out-Null
}

# 4) Перезапуск USB host controllers / root hubs
Get-PnpDevice -Class USB | Where-Object {
  $_.FriendlyName -match 'Root Hub|Host Controller|корнев|хост-контроллер|Корневой|Хост'
} | ForEach-Object {
  Disable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false
  Start-Sleep -Milliseconds 500
  Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false
}

# 5) Убедиться, что автоподключение томов включено, и убрать мусорные точки
"automount enable" | diskpart | Out-Null
& mountvol.exe /R 2>$null | Out-Null

# 6) Гарантировать корректный тип запуска драйверов хранилища
foreach ($svc in 'USBSTOR') {
  $p = "HKLM:\SYSTEM\CurrentControlSet\Services\$svc"
  if (Test-Path $p) { Set-ItemProperty $p -Name Start -Value 3 -ErrorAction SilentlyContinue }
}

# 7) Перескан шины
& pnputil.exe /scan-devices 2>$null | Out-Null
Start-Sleep -Seconds 2

$okK = @(Get-PnpDevice -Class Keyboard | Where-Object Status -eq 'OK').Count
$okM = @(Get-PnpDevice -Class Mouse | Where-Object Status -eq 'OK').Count
$badInput = @(Get-PnpDevice -Class Keyboard,Mouse,HIDClass | Where-Object { $_.Status -ne 'OK' -and $_.Status -ne 'Unknown' }).Count
Write-Output "OK_KEYBOARDS=$okK"
Write-Output "OK_MICE=$okM"
Write-Output "PROBLEM_INPUT=$badInput"
"""


def _reset_enum_owner_to_system() -> list[str]:
    """Возвращает владельца веток Enum службе SYSTEM (через WinAPI)."""
    notes: list[str] = []
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        SE_REGISTRY_KEY = 4
        OWNER_SECURITY_INFORMATION = 0x00000001
        WinLocalSystemSid = 22

        advapi32.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, ctypes.c_uint, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

        size = wintypes.DWORD(0)
        advapi32.CreateWellKnownSid(WinLocalSystemSid, None, None, ctypes.byref(size))
        buf = (ctypes.c_char * max(size.value, 64))()
        if not advapi32.CreateWellKnownSid(
            WinLocalSystemSid, None, buf, ctypes.byref(size)
        ):
            return notes
        sid = ctypes.cast(buf, ctypes.c_void_p)

        for root in (
            r"MACHINE\SYSTEM\CurrentControlSet\Enum\USB",
            r"MACHINE\SYSTEM\CurrentControlSet\Enum\USBSTOR",
        ):
            rc = advapi32.SetNamedSecurityInfoW(
                root, SE_REGISTRY_KEY, OWNER_SECURITY_INFORMATION,
                sid, None, None, None,
            )
            if rc == 0:
                notes.append(f"owner->SYSTEM: {root}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"reset owner: {exc}")
    return notes


def repair_usb(progress: Callable[[str], None] | None = None) -> list[str]:
    """
    Полное восстановление: ввод (клавиатура/мышь) + накопители (флешки).
    """
    log = progress or (lambda _m: None)
    notes: list[str] = []

    log("Восстановление: сброс владельца веток Enum на SYSTEM…")
    for n in _reset_enum_owner_to_system():
        notes.append(n)
        log(n)

    log("Восстановление: удаление phantom-устройств, перезапуск USB, автоподключение…")
    rc, out = _powershell(_REPAIR_PS)
    for line in out.splitlines():
        line = line.strip()
        if line:
            notes.append(line)
            log(line)
    if rc != 0 and not out:
        notes.append(f"powershell exit {rc}")

    tail = (
        "Если USB-клавиатура/мышь/флешка всё ещё не работают: переподключите "
        "кабель или перезагрузите ПК."
    )
    notes.append(tail)
    log(tail)
    return notes


# Обратная совместимость со старым именем
def repair_usb_input(progress: Callable[[str], None] | None = None) -> list[str]:
    return repair_usb(progress=progress)
