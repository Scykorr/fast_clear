"""Очистка файловых артефактов: SetupAPI, Prefetch, история консоли."""

from __future__ import annotations

import glob
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_WIN = Path(os.environ.get("SystemRoot", r"C:\Windows"))

SETUPAPI_FILES = (
    _WIN / "INF" / "setupapi.dev.log",
    _WIN / "INF" / "setupapi.app.log",
    _WIN / "INF" / "setupapi.setup.log",
    _WIN / "INF" / "setupapi.offline.log",
    _WIN / "setupact.log",
    _WIN / "setuperr.log",
)

# Ротированные логи setupapi (setupapi.dev.20240101_120000.log и т.п.)
SETUPAPI_GLOBS = (
    str(_WIN / "INF" / "setupapi.dev.*.log"),
    str(_WIN / "INF" / "setupapi.app.*.log"),
    str(_WIN / "INF" / "setupapi*.log.*"),
)

# Amcache — хранит сведения об устройствах/программах, включая USB
AMCACHE_FILES = (
    _WIN / "AppCompat" / "Programs" / "Amcache.hve",
)

PREFETCH_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Prefetch"

# Имена Prefetch, связанные с очисткой журналов / USB-историей
PREFETCH_PATTERNS = (
    "WEVTUTIL",
    "FAST_CLEAR",
    "USBDEVIEW",
    "PRIVAZER",
    "GARMIN",
    "APPLEMOBILE",
    "ADB.EXE",
)



@dataclass
class FileCleanResult:
    truncated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _truncate_file(path: Path) -> None:
    """Обнуляет файл, сохраняя его существование (SetupAPI так спокойнее)."""
    with open(path, "w", encoding="utf-8", errors="ignore"):
        pass


def clear_setupapi_logs(
    progress: Callable[[str], None] | None = None,
) -> FileCleanResult:
    log = progress or (lambda _m: None)
    result = FileCleanResult()

    for path in SETUPAPI_FILES:
        if not path.is_file():
            continue
        log(f"Файл: обнуление {path}")
        try:
            _truncate_file(path)
            result.truncated.append(str(path))
        except OSError as exc:
            result.errors.append(f"{path}: {exc}")

    # Ротированные копии — удаляем целиком
    for pattern in SETUPAPI_GLOBS:
        for match in glob.glob(pattern):
            p = Path(match)
            if p in SETUPAPI_FILES or not p.is_file():
                continue
            log(f"Файл: удаление {p.name}")
            try:
                p.unlink()
                result.deleted.append(str(p))
            except OSError as exc:
                result.errors.append(f"{p}: {exc}")

    result_amcache = clear_amcache(progress=progress)
    result.deleted.extend(result_amcache.deleted)
    result.truncated.extend(result_amcache.truncated)
    result.errors.extend(result_amcache.errors)
    return result


_AMCACHE_TARGET = (
    "USBSTOR",
    "USB\\VID",
    "USB#VID",
    "SWD\\WPDBUSENUM",
    "SWD#WPDBUSENUM",
    "WPDBUSENUM",
    "STORAGE\\VOLUME",
    "MTP",
    "GARMIN",
    "VID_0781",  # SanDisk и т.п. — общий VID-признак ниже
)
_AMCACHE_VIDS = (
    "VID_0781", "VID_05AC", "VID_091E", "VID_04E8", "VID_18D1", "VID_0951",
    "VID_8564", "VID_090C", "VID_13FE", "VID_058F", "VID_1F75",
)


def clear_amcache(
    progress: Callable[[str], None] | None = None,
) -> FileCleanResult:
    """
    Best-effort очистка Amcache.hve от записей USB/портативных устройств.
    Загружает hive офлайн (reg load), удаляет ветки устройств, выгружает.
    Если файл заблокирован системой — пропускает без ошибки.
    """
    import subprocess
    import winreg

    log = progress or (lambda _m: None)
    result = FileCleanResult()

    hive = None
    for path in AMCACHE_FILES:
        if path.is_file():
            hive = path
            break
    if hive is None:
        return result

    mount = "FASTCLEAR_AMC"
    load = subprocess.run(
        ["reg.exe", "load", rf"HKLM\{mount}", str(hive)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if load.returncode != 0:
        log("Amcache: занят системой, пропуск (несущественно)")
        return result

    def _match(name: str) -> bool:
        up = name.upper()
        if any(t in up for t in _AMCACHE_TARGET):
            return True
        return any(v in up for v in _AMCACHE_VIDS)

    try:
        for branch in ("InventoryDevicePnp", "InventoryDeviceContainer", "Root\\InventoryDevicePnp"):
            base = rf"{mount}\\Root\\{branch}" if not branch.startswith("Root") else rf"{mount}\\{branch}"
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base.replace("\\\\", "\\"), 0, winreg.KEY_READ)
            except OSError:
                continue
            subs = []
            i = 0
            while True:
                try:
                    subs.append(winreg.EnumKey(key, i)); i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
            removed = 0
            for sub in subs:
                if _match(sub):
                    full = base.replace("\\\\", "\\") + "\\" + sub
                    d = subprocess.run(
                        ["reg.exe", "delete", rf"HKLM\{full}", "/f"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", check=False,
                    )
                    if d.returncode == 0:
                        removed += 1
            if removed:
                log(f"Amcache: удалено записей в {branch}: {removed}")
                result.deleted.append(f"Amcache\\{branch} ({removed})")
    finally:
        subprocess.run(
            ["reg.exe", "unload", rf"HKLM\{mount}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    return result


def clear_prefetch(
    progress: Callable[[str], None] | None = None,
    patterns: tuple[str, ...] = PREFETCH_PATTERNS,
) -> FileCleanResult:
    log = progress or (lambda _m: None)
    result = FileCleanResult()
    if not PREFETCH_DIR.is_dir():
        return result

    for entry in PREFETCH_DIR.iterdir():
        if not entry.is_file():
            continue
        name = entry.name.upper()
        if not any(p in name for p in patterns):
            continue
        log(f"Prefetch: удаление {entry.name}")
        try:
            entry.unlink()
            result.deleted.append(str(entry))
        except OSError as exc:
            result.errors.append(f"{entry}: {exc}")
    return result


def clear_powershell_history(
    progress: Callable[[str], None] | None = None,
) -> FileCleanResult:
    log = progress or (lambda _m: None)
    result = FileCleanResult()
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return result

    history = (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "PowerShell"
        / "PSReadLine"
        / "ConsoleHost_history.txt"
    )
    if history.is_file():
        log(f"История: обнуление {history}")
        try:
            _truncate_file(history)
            result.truncated.append(str(history))
        except OSError as exc:
            result.errors.append(f"{history}: {exc}")
    return result


def clear_temp_traces(
    progress: Callable[[str], None] | None = None,
) -> FileCleanResult:
    """Удаляет временные файлы с именами, похожими на fast_clear / wevtutil."""
    log = progress or (lambda _m: None)
    result = FileCleanResult()
    roots = {
        Path(tempfile.gettempdir()),
        Path(os.environ.get("TEMP", "")),
        Path(os.environ.get("TMP", "")),
    }
    markers = ("fast_clear", "wevtutil", "usb_clean")
    for root in roots:
        if not root or not root.is_dir():
            continue
        try:
            for entry in root.iterdir():
                low = entry.name.lower()
                if any(m in low for m in markers):
                    log(f"Temp: удаление {entry}")
                    try:
                        if entry.is_file():
                            entry.unlink()
                            result.deleted.append(str(entry))
                    except OSError as exc:
                        result.errors.append(f"{entry}: {exc}")
        except OSError:
            continue
    return result
