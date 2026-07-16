"""Очистка файловых артефактов: SetupAPI, Prefetch, история консоли."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SETUPAPI_FILES = (
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "INF" / "setupapi.dev.log",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "INF" / "setupapi.app.log",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "setupact.log",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "setuperr.log",
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
