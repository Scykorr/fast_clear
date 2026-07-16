"""Очистка журналов событий Windows, связанных с USB и фактом очистки."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable

# Каналы: PnP / USB / накопители / MTP / WPD / модемы / WWAN
USB_RELATED_CHANNELS: tuple[str, ...] = (
    "Microsoft-Windows-DriverFrameworks-UserMode/Operational",
    "Microsoft-Windows-Kernel-PnP/Configuration",
    "Microsoft-Windows-Kernel-PnP/Device Configuration",
    "Microsoft-Windows-Kernel-PnP/Device Management",
    "Microsoft-Windows-Partition/Diagnostic",
    "Microsoft-Windows-Storage-ClassPnP/Operational",
    "Microsoft-Windows-DeviceSetupManager/Admin",
    "Microsoft-Windows-DeviceSetupManager/Operational",
    "Microsoft-Windows-Storsvc/Diagnostic",
    "Microsoft-Windows-StorageManagement/Operational",
    "Microsoft-Windows-Volume/Diagnostic",
    "Microsoft-Windows-Ntfs/Operational",
    "Microsoft-Windows-Shell-Core/Operational",
    "Microsoft-Windows-WPD-ClassInstaller/Operational",
    "Microsoft-Windows-WPD-API/Operational",
    "Microsoft-Windows-WPD-CompositeBus/Operational",
    "Microsoft-Windows-WPD-MTPClassDriver/Operational",
    "Microsoft-Windows-WPD-MTPUS/Operational",
    "Microsoft-Windows-Media-Streaming/Operational",
    "Microsoft-Windows-WWAN-SVC-EVENTS/Operational",
    "Microsoft-Windows-WWAN-MMC/Operational",
    "Microsoft-Windows-Mobile-Broadband-Experience-Api/Operational",
    "Microsoft-Windows-Mobile-Broadband-Experience-Parser-Service/Operational",
    "Microsoft-Windows-Mobile-Broadband-Experience-SmsApi/Operational",
    "Microsoft-Windows-ModemDeviceEvents/Operational",
)

# Журналы, в которых остаётся Event ID 104/1102 («журнал очищен»)
AUDIT_CHANNELS: tuple[str, ...] = (
    "System",
    "Security",
    "Application",
    "Microsoft-Windows-Eventlog/Operational",
    "Microsoft-Windows-Eventlog/Admin",
    "Setup",
)

# Полный список для финального прохода (USB + следы очистки)
ALL_CLEAR_CHANNELS: tuple[str, ...] = tuple(
    dict.fromkeys((*USB_RELATED_CHANNELS, *AUDIT_CHANNELS))
)


@dataclass
class EventLogResult:
    cleared: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _wevtutil(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wevtutil.exe", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def channel_exists(name: str) -> bool:
    proc = _wevtutil("gl", name)
    return proc.returncode == 0


def clear_channel(name: str) -> tuple[bool, str]:
    """Очищает канал. Возвращает (успех, сообщение)."""
    if not channel_exists(name):
        return False, "missing"
    proc = _wevtutil("cl", name)
    if proc.returncode == 0:
        return True, "ok"
    err = (proc.stderr or proc.stdout or "").strip()
    return False, err or f"exit {proc.returncode}"


def clear_event_logs(
    channels: tuple[str, ...] | None = None,
    progress: Callable[[str], None] | None = None,
) -> EventLogResult:
    log = progress or (lambda _m: None)
    result = EventLogResult()
    targets = channels or ALL_CLEAR_CHANNELS

    for name in targets:
        log(f"Журнал: {name}")
        ok, info = clear_channel(name)
        if ok:
            result.cleared.append(name)
        elif info == "missing":
            result.missing.append(name)
        else:
            result.failed.append(f"{name}: {info}")

    return result


def clear_audit_traces(
    progress: Callable[[str], None] | None = None,
) -> EventLogResult:
    """
    Повторная очистка журналов, куда Windows пишет факт очистки других журналов
    (System/104, Security/1102 и т.п.).
    """
    return clear_event_logs(AUDIT_CHANNELS, progress=progress)
