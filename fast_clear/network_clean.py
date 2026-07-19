"""Очистка истории сетей: Wi-Fi и факты подключения к Интернету.

Основную «историю подключений», которую показывают детекторы (SSID, MAC, дата/
время, «Интернет есть/отсутствует»), Windows держит в журналах событий
(WLAN-AutoConfig/Operational, UniversalTelemetryClient/Operational и т.п.) — они
стираются в eventlog_clean. Здесь дочищаются реестровые следы NetworkList
(имена сетей, даты первого/последнего подключения) и, опционально, XML-профили
Wi-Fi (сохранённые сети с паролями).
"""

from __future__ import annotations

import os
import subprocess
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_NL = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList"

# Ключи реестра с историей сетей (имена, даты, сигнатуры)
NETWORKLIST_KEYS = (
    rf"{_NL}\Profiles",
    rf"{_NL}\Signatures\Managed",
    rf"{_NL}\Signatures\Unmanaged",
    rf"{_NL}\Nla\Cache\Intranet",
    rf"{_NL}\Nla\Wireless",
)

WLAN_PROFILE_DIR = (
    Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    / "Microsoft"
    / "Wlansvc"
    / "Profiles"
    / "Interfaces"
)


@dataclass
class NetworkCleanResult:
    deleted_keys: list[str] = field(default_factory=list)
    deleted_profiles: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _enum_subkeys(root, path: str) -> list[str]:
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            out, i = [], 0
            while True:
                try:
                    out.append(winreg.EnumKey(key, i)); i += 1
                except OSError:
                    break
            return out
    except OSError:
        return []


def _delete_key_tree(path: str, result: NetworkCleanResult) -> None:
    full = rf"HKLM\{path}"
    proc = subprocess.run(
        ["reg.exe", "delete", full, "/f"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode == 0:
        result.deleted_keys.append(path)
    else:
        err = (proc.stderr or proc.stdout or "").strip()
        if "не удается найти" not in err.lower() and "unable to find" not in err.lower():
            result.errors.append(f"{path}: {err[:160]}")


def clean_network_history(
    progress: Callable[[str], None] | None = None,
    remove_wlan_profiles: bool = False,
) -> NetworkCleanResult:
    """
    Чистит реестровые следы сетей NetworkList. При remove_wlan_profiles=True
    также удаляет сохранённые Wi-Fi профили (сбросит пароли сетей!).
    """
    log = progress or (lambda _m: None)
    result = NetworkCleanResult()

    for base in NETWORKLIST_KEYS:
        subs = _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, base)
        if not subs:
            continue
        log(f"Сеть: очистка {base} ({len(subs)} записей)")
        for sub in subs:
            _delete_key_tree(f"{base}\\{sub}", result)

    if remove_wlan_profiles and WLAN_PROFILE_DIR.is_dir():
        for iface in WLAN_PROFILE_DIR.iterdir():
            if not iface.is_dir():
                continue
            for xml in iface.glob("*.xml"):
                log(f"Сеть: удаление Wi-Fi профиля {xml.name}")
                try:
                    xml.unlink()
                    result.deleted_profiles.append(str(xml))
                except OSError as exc:
                    result.errors.append(f"{xml}: {exc}")

    return result
