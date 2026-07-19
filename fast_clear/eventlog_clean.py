"""Очистка журналов событий Windows, связанных с USB и фактом очистки."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

WINEVT_LOGS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "winevt" / "Logs"

# Каналы: PnP / USB / накопители / MTP / WPD / модемы / WWAN
# Помечены (HC) те, что читает программа-детектор HistoryChecker.
USB_RELATED_CHANNELS: tuple[str, ...] = (
    "Microsoft-Windows-DriverFrameworks-UserMode/Operational",  # HC
    "Microsoft-Windows-Kernel-PnP/Configuration",  # HC
    "Microsoft-Windows-Kernel-PnPConfig/Configuration",  # HC (вариант)
    "Microsoft-Windows-Kernel-PnP/Device Configuration",
    "Microsoft-Windows-Kernel-PnP/Device Management",
    "Microsoft-Windows-Partition/Diagnostic",  # HC (Event 1006: VID/PID/serial/model)
    "Microsoft-Windows-Storage-ClassPnP/Operational",
    "Microsoft-Windows-DeviceSetupManager/Admin",  # HC
    "Microsoft-Windows-DeviceSetupManager/Operational",
    "Microsoft-Windows-Storsvc/Diagnostic",  # HC
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

# Каналы истории сети: Wi-Fi и факты подключения к Интернету.
# WLAN-AutoConfig/Operational -> вкладка «Сети WiFi» (SSID, MAC, время);
# UniversalTelemetryClient/Operational -> вкладка «Факты подключения к Интернет».
NETWORK_CHANNELS: tuple[str, ...] = (
    "Microsoft-Windows-WLAN-AutoConfig/Operational",  # HC (Wi-Fi)
    "Microsoft-Windows-WLAN-AutoConfig/Diagnostic",
    "Microsoft-Windows-UniversalTelemetryClient/Operational",  # HC (Интернет)
    "Microsoft-Windows-NCSI/Operational",
    "Microsoft-Windows-NetworkProfile/Operational",
    "Microsoft-Windows-Dhcp-Client/Admin",
    "Microsoft-Windows-Dhcpv6-Client/Admin",
    "Microsoft-Windows-Wcmsvc/Operational",
    "Microsoft-Windows-WFP/Operational",
    "Microsoft-Windows-NlaSvc/Operational",
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

# Полный список для финального прохода (USB + сеть + следы очистки)
ALL_CLEAR_CHANNELS: tuple[str, ...] = tuple(
    dict.fromkeys((*USB_RELATED_CHANNELS, *NETWORK_CHANNELS, *AUDIT_CHANNELS))
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


def _channel_to_filename(name: str) -> str:
    """System -> System.evtx; A/B -> A%4B.evtx (как в winevt\\Logs)."""
    fname = name.replace("/", "%4").replace("\\", "%4")
    return f"{fname}.evtx"


def _sc(*args: str, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["sc.exe", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _powershell(script: str, timeout: int = 90) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _stop_eventlog() -> bool:
    _powershell("Stop-Service -Name EventLog -Force -ErrorAction SilentlyContinue")
    for _ in range(20):
        rc, out = _powershell(
            "(Get-Service EventLog).Status"
        )
        if "Stopped" in out:
            return True
        time.sleep(0.5)
    return False


def _start_eventlog() -> bool:
    _powershell("Start-Service -Name EventLog -ErrorAction SilentlyContinue")
    for _ in range(20):
        rc, out = _powershell("(Get-Service EventLog).Status")
        if "Running" in out:
            return True
        time.sleep(0.5)
    return False


def wipe_logs_via_service(
    channels: tuple[str, ...] | None = None,
    progress: Callable[[str], None] | None = None,
) -> EventLogResult:
    """
    Останавливает службу журналов, удаляет .evtx целиком и запускает службу.
    Это НЕ оставляет Event ID 104/1102 «журнал очищен» (в отличие от wevtutil cl).
    При невозможности остановить службу — откат на wevtutil.
    """
    log = progress or (lambda _m: None)
    result = EventLogResult()
    targets = channels or ALL_CLEAR_CHANNELS

    log("Журналы: остановка службы EventLog…")
    if not _stop_eventlog():
        log("Журналы: не удалось остановить службу — использую wevtutil (останется 104)")
        return clear_event_logs(targets, progress=progress)

    try:
        for name in targets:
            fpath = WINEVT_LOGS / _channel_to_filename(name)
            if not fpath.exists():
                result.missing.append(name)
                continue
            try:
                # усечение до нуля надёжнее удаления (файл открыт службой не всегда)
                try:
                    fpath.unlink()
                except OSError:
                    with open(fpath, "wb"):
                        pass
                result.cleared.append(name)
                log(f"Журнал (файл): {name}")
            except OSError as exc:
                result.failed.append(f"{name}: {exc}")
    finally:
        log("Журналы: запуск службы EventLog…")
        started = _start_eventlog()
        if not started:
            log("Журналы: ВНИМАНИЕ — служба EventLog не запустилась, требуется перезагрузка")
            result.failed.append("EventLog service did not restart")

    return result
