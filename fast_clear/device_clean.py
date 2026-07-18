"""Удаление истории устройств через pnputil (безопасно для PnP).

Работает только с НЕ подключёнными (phantom) устройствами и только с
целевыми классами: накопители, телефоны, часы (Garmin), модемы, WPD/MTP.
Никогда не трогает клавиатуры, мыши, HID, USB-хабы, Bluetooth, звук, камеры.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable

# Классы устройств, которые НЕЛЬЗЯ удалять ни при каких условиях
PROTECTED_CLASSES = {
    "KEYBOARD",
    "MOUSE",
    "HIDCLASS",
    "HID",
    "SYSTEM",
    "USB",  # контроллеры/хабы (класс USB = host controller/hub)
    "BLUETOOTH",
    "AUDIOENDPOINT",
    "MEDIA",
    "AUDIO",
    "CAMERA",
    "IMAGE",
    "MONITOR",
    "DISPLAY",
    "NET",  # физические сетевые карты — трогаем только явные USB-модемы по InstanceId
    "PROCESSOR",
    "COMPUTER",
    "SOFTWAREDEVICE",
}

PROTECTED_HINT_RE = re.compile(
    r"(HID|KEYBOARD|KEYBORD|MOUSE|\bMICE\b|ROOT_HUB|USBHUB|GENERIC.?HUB|"
    r"BLUETOOTH|BTHENUM|BTHUSB|AUDIO|HEADSET|SPEAKER|MICROPHONE|"
    r"WEBCAM|CAMERA|\bVIDEO\b|TOUCHPAD|TOUCHSCREEN|DIGITIZER|SENSOR|"
    r"HOST.?CONTROLLER|COMPOSITE.?DEVICE)",
    re.IGNORECASE,
)

# Целевые устройства (только их удаляем)
TARGET_INSTANCE_RE = re.compile(
    r"("
    r"^USBSTOR\\|"
    r"^STORAGE\\VOLUME\\_\?\?_USBSTOR|"
    r"^SWD\\WPDBUSENUM\\|"
    r"^WPD\\|"
    r"^MODEM\\|"
    r"^UMB\\|"
    r"^SWD\\MSMMB\\"
    r")",
    re.IGNORECASE,
)

TARGET_HINT_RE = re.compile(
    r"(USBSTOR|MASS.?STORAGE|FLASH|REMOVABLE|MTP|\bWPD\b|PORTABLE|"
    r"GARMIN|APPLE|IPHONE|IPAD|IPOD|ANDROID|SAMSUNG|XIAOMI|HUAWEI|"
    r"ONEPLUS|PIXEL|NOKIA|MOTOROLA|OPPO|VIVO|REALME|SMARTPHONE|"
    r"\bPHONE\b|MODEM|WWAN|MBIM|RNDIS|CDC.?ACM|CDC.?NCM|TETHER|"
    r"SANDISK|KINGSTON|TRANSCEND|CORSAIR|VERBATIM|LEXAR|TOSHIBA|"
    r"SD.?CARD|CARD.?READER|UDISK|USB.?DISK|WATCH|FORERUNNER|FENIX|VENU)",
    re.IGNORECASE,
)

# VID известных телефонов / часов / модемов / флешек
TARGET_VIDS = {
    "0781",  # SanDisk
    "05AC",  # Apple
    "091E",  # Garmin
    "04E8",  # Samsung
    "18D1",  # Google
    "22B8",  # Motorola
    "0FCE",  # Sony
    "12D1",  # Huawei
    "2717",  # Xiaomi
    "2A70",  # OnePlus
    "0E8D",  # MediaTek
    "19D2",  # ZTE modem
    "1199",  # Sierra Wireless
    "1BBB",  # T&A Mobile
    "0930",  # Toshiba
    "058F",  # Alcor (card readers/flash)
    "0951",  # Kingston
    "8564",  # Transcend
    "090C",  # Silicon Motion (flash)
    "1F75",  # Innostor (flash)
    "13FE",  # Kingston/Phison flash
}


@dataclass
class DeviceCleanResult:
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
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
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _powershell(script: str, timeout: int = 90) -> tuple[int, str]:
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


def list_disconnected_devices() -> list[dict]:
    """Список НЕ подключённых устройств (InstanceId, Class, FriendlyName)."""
    script = (
        "Get-PnpDevice -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Status -eq 'Unknown' } | "
        "Select-Object InstanceId, Class, FriendlyName | ConvertTo-Json -Compress"
    )
    rc, out = _powershell(script)
    if rc != 0 or not out:
        return []
    start = out.find("[")
    obj_start = out.find("{")
    if start == -1 and obj_start == -1:
        return []
    text = out[start:] if start != -1 else out[obj_start:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "InstanceId": item.get("InstanceId") or "",
                "Class": (item.get("Class") or "").upper(),
                "FriendlyName": item.get("FriendlyName") or "",
            }
        )
    return result


def _vid_of(text: str) -> str | None:
    m = re.search(r"VID_([0-9A-Fa-f]{4})", text)
    return m.group(1).upper() if m else None


def is_protected_device(dev: dict) -> bool:
    inst = dev.get("InstanceId", "")
    cls = dev.get("Class", "").upper()
    fname = dev.get("FriendlyName", "")
    blob = f"{inst} {fname}"
    if PROTECTED_HINT_RE.search(blob):
        return True
    # Класс USB (хабы/контроллеры) защищаем, КРОМЕ явных накопителей по InstanceId
    if cls in PROTECTED_CLASSES:
        if cls == "USB" and re.match(
            r"^USB\\VID_", inst, re.IGNORECASE
        ) and _is_storage_or_portable(blob, inst):
            return False
        if cls == "NET" and re.search(r"WWAN|RNDIS|MBIM|MODEM|USB\\VID_", blob, re.I):
            return False
        return True
    return False


def _is_storage_or_portable(blob: str, inst: str) -> bool:
    if TARGET_HINT_RE.search(blob):
        return True
    vid = _vid_of(blob) or _vid_of(inst)
    return bool(vid and vid in TARGET_VIDS)


def is_target_device(dev: dict) -> bool:
    inst = dev.get("InstanceId", "")
    cls = dev.get("Class", "").upper()
    fname = dev.get("FriendlyName", "")
    blob = f"{inst} {fname}"

    if is_protected_device(dev):
        return False

    if TARGET_INSTANCE_RE.search(inst):
        return True
    if cls in {"DISKDRIVE", "WPD", "MODEM"}:
        return True
    if cls in {"PORTS", "PORT"} and _is_storage_or_portable(blob, inst):
        return True
    if re.match(r"^USB\\VID_", inst, re.IGNORECASE) and _is_storage_or_portable(
        blob, inst
    ):
        return True
    return False


def _remove_device(instance_id: str) -> tuple[bool, str]:
    rc, out = _run(["pnputil", "/remove-device", instance_id])
    if rc == 0:
        return True, "ok"
    # fallback через PowerShell
    safe = instance_id.replace("'", "''")
    rc2, out2 = _powershell(
        f"$ErrorActionPreference='SilentlyContinue';"
        f"Remove-PnpDevice -InstanceId '{safe}' -Confirm:$false;"
        f"if ($?) {{ 'ok' }} else {{ 'fail' }}"
    )
    if rc2 == 0 and "ok" in out2.lower():
        return True, "ok(ps)"
    return False, (out or out2 or "remove failed").splitlines()[0][:200]


def clean_device_history(
    progress: Callable[[str], None] | None = None,
) -> DeviceCleanResult:
    """Удаляет phantom-устройства (флешки/телефоны/часы/модемы) через pnputil."""
    log = progress or (lambda _m: None)
    result = DeviceCleanResult()

    devices = list_disconnected_devices()
    log(f"Устройства: найдено отключённых (phantom): {len(devices)}")

    for dev in devices:
        inst = dev["InstanceId"]
        if not inst:
            continue
        if is_target_device(dev):
            ok, info = _remove_device(inst)
            short = inst if len(inst) <= 80 else inst[:77] + "…"
            if ok:
                result.removed.append(inst)
                log(f"Устройства: удалено {short}")
            else:
                result.errors.append(f"{short}: {info}")
                log(f"Устройства: ошибка {short} ({info})")
        else:
            result.skipped.append(inst)

    return result
