"""Очистка реестра от истории USB / MTP / модемов / телефонов / часов.

ВАЖНО: не трогает клавиатуры, мыши, HID и USB-хабы.
"""

from __future__ import annotations

import re
import winreg
from dataclasses import dataclass, field
from typing import Callable

from fast_clear.reg_acl import force_delete_hklm_tree

# Только классы, где безопасно вычищать портативные следы (НЕ общий USB HID)
DEVICE_CLASS_GUIDS = (
    "{53f56307-b6bf-11d0-94f2-00a0c91efb8b}",  # Disk
    "{53f5630d-b6bf-11d0-94f2-00a0c91efb8b}",  # Volume
    "{4d36e96d-e325-11ce-bfc1-08002be10318}",  # Modem
    "{4d36e978-e325-11ce-bfc1-08002be10318}",  # Ports (COM) — только USB-модемы по фильтру
    "{4d36e972-e325-11ce-bfc1-08002be10318}",  # Net — USB tethering / WWAN по фильтру
    "{eec5ad98-8080-425f-922a-dabf3de3f69a}",  # WPD
    "{6ac27878-a6bc-11d0-96b8-00a0c91ede8a}",  # WPD (alt)
    "{6bdd1fc6-810f-11d0-bec7-08002be2092f}",  # StillImage / WIA
    "{50dd5230-ba8a-11d1-bf5d-0000f805f530}",  # SmartCardReader / CCID
)

# Полная очистка — без HID/хабов
ENUM_FULL_WIPE = (
    r"SYSTEM\CurrentControlSet\Enum\USBSTOR",
    r"SYSTEM\CurrentControlSet\Enum\USBPRINT",
    r"SYSTEM\CurrentControlSet\Enum\WPD",
    r"SYSTEM\CurrentControlSet\Enum\SWD\WPDBUSENUM",
    r"SYSTEM\CurrentControlSet\Enum\Modem",
    r"SYSTEM\CurrentControlSet\Enum\UMB",
    r"SYSTEM\CurrentControlSet\Enum\SWD\MSMMB",
)

# Выборочная очистка (сохраняем input / hubs)
ENUM_SELECTIVE = (
    r"SYSTEM\CurrentControlSet\Enum\USB",
    r"SYSTEM\CurrentControlSet\Enum\SCSI",
)

EXTRA_KEYS_HKLM = (
    r"SOFTWARE\Microsoft\Windows Portable Devices\Devices",
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\EMDMgmt",
    r"SYSTEM\CurrentControlSet\Control\usbflags",
    r"SYSTEM\CurrentControlSet\Services\USBSTOR\Enum",
    r"SYSTEM\CurrentControlSet\Services\Wudfrd\Enum",
    r"SYSTEM\CurrentControlSet\Services\Modem\Enum",
    r"SYSTEM\CurrentControlSet\Services\usbser\Enum",
    r"SYSTEM\CurrentControlSet\Services\WUDFWpdFs\Enum",
    r"SYSTEM\CurrentControlSet\Services\WpdUpFltr\Enum",
    r"SYSTEM\CurrentControlSet\Services\WudfUsbccidDriver\Enum",
    r"SYSTEM\CurrentControlSet\Services\WWANSvc\Enum",
    # НЕ чистим Services\Usbccgp\Enum и WinUsb\Enum целиком — там бывают HID-композиты
)

VENDOR_SOFTWARE_KEYS = (
    r"SOFTWARE\Apple Inc.\Apple Mobile Device Support",
    r"SOFTWARE\WOW6432Node\Apple Inc.\Apple Mobile Device Support",
    r"SOFTWARE\Garmin",
    r"SOFTWARE\WOW6432Node\Garmin",
    r"SOFTWARE\Samsung Electronics",
    r"SOFTWARE\WOW6432Node\Samsung Electronics",
    r"SOFTWARE\Android Debug Bridge",
    r"SOFTWARE\WOW6432Node\Android Debug Bridge",
)

EXTRA_KEYS_HKCU = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2",
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers\KnownDevices",
)

BAM_PATH = r"SYSTEM\CurrentControlSet\Services\bam\State\UserSettings"

# Защищённые устройства ввода / хабы — НИКОГДА не удалять
PROTECTED_RE = re.compile(
    r"("
    r"ROOT_HUB|USBHUB|HUB_CLASS|CLASS_09|"
    r"CLASS_03|HIDUSB|KBDHID|MOUHID|HIDCLASS|"
    r"KEYBOARD|KEYBORD|MOUSE|MICE|"  # KEYBORD — частая опечатка в INF
    r"HID[\s_\-]?COMPLIANT|HID[\s_\-]?KEYBOARD|HID[\s_\-]?MOUSE|"
    r"INPUT[\s_\-]?DEVICE|USER[\s_\-]?INPUT|"
    r"TRACKBALL|TOUCHPAD|TOUCH[\s_\-]?SCREEN|DIGITIZER|"
    r"GAME[\s_\-]?CONTROLLER|JOYSTICK|XBOX|GAMEPAD|"  # оставляем геймпады
    r"BLUETOOTH|BTHUSB|BTHENUM|"
    r"AUDIO|HEADSET|WEBCAM|CAMERA|VIDEO|"  # не ломаем периферию рабочего места
    r"COMPOSITE[\s_\-]?PARENT"  # осторожно: проверяется отдельно
    r")",
    re.IGNORECASE,
)

# Целевые портативные устройства (без голого «USB» — иначе снесёт всё)
TARGET_RE = re.compile(
    r"("
    r"USBSTOR|WPDBUSENUM|MTP|WPD#|WPD\\|"
    r"CLASS_08|CLASS_06|CLASS_02|"  # mass storage / still image / CDC
    r"MODEM|WWAN|MBB|MBIM|QMI|RNDIS|CDC_ACM|CDC_NCM|CDC_ECM|"
    r"GARMIN|APPLE|IPHONE|IPAD|IPOD|ANDROID|SAMSUNG|XIAOMI|HUAWEI|"
    r"ONEPLUS|PIXEL|NOKIA|MOTOROLA|OPPO|VIVO|REALME|"
    r"MOBILE\s*PHONE|SMARTPHONE|HANDHELD|"
    r"TETHER|HOTSPOT|MASS\s*STORAGE|FLASH\s*DRIVE|THUMB\s*DRIVE|"
    r"REMOVABLE|DISK&VEN|USBSTOR#|"
    r"USBSER|SERIAL\s*MODEM|LTE|3G|4G|5G\s*MODEM"
    r")",
    re.IGNORECASE,
)

# VID известных телефонов / часов / модемов (дополнительный сигнал)
TARGET_VIDS = {
    "05AC",  # Apple
    "091E",  # Garmin
    "04E8",  # Samsung
    "18D1",  # Google
    "22B8",  # Motorola
    "0FCE",  # Sony Ericsson / Sony
    "12D1",  # Huawei
    "2717",  # Xiaomi
    "2A70",  # OnePlus
    "0E8D",  # MediaTek phones
    "19D2",  # ZTE modem
    "12D1",  # Huawei modem
    "1199",  # Sierra Wireless
    "12D1",
    "1BBB",  # T&A Mobile
    "04E8",
}


@dataclass
class CleanResult:
    deleted_keys: list[str] = field(default_factory=list)
    deleted_values: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "CleanResult") -> None:
        self.deleted_keys.extend(other.deleted_keys)
        self.deleted_values.extend(other.deleted_values)
        self.skipped.extend(other.skipped)
        self.errors.extend(other.errors)


def _open_key(hive: int, path: str, access: int = winreg.KEY_READ):
    return winreg.OpenKey(hive, path, 0, access | winreg.KEY_WOW64_64KEY)


def _enum_subkeys(hive: int, path: str) -> list[str]:
    try:
        with _open_key(hive, path) as key:
            result = []
            i = 0
            while True:
                try:
                    result.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
            return result
    except FileNotFoundError:
        return []
    except OSError:
        return []


def _enum_values(hive: int, path: str) -> list[tuple[str, object, int]]:
    try:
        with _open_key(hive, path) as key:
            result = []
            i = 0
            while True:
                try:
                    result.append(winreg.EnumValue(key, i))
                    i += 1
                except OSError:
                    break
            return result
    except (FileNotFoundError, OSError):
        return []


def _query_str(hive: int, path: str, name: str) -> str:
    try:
        with _open_key(hive, path) as key:
            val, _ = winreg.QueryValueEx(key, name)
            return str(val) if val is not None else ""
    except OSError:
        return ""


def _device_blob(hive: int, path: str, *extra: str) -> str:
    parts = list(extra)
    for name in (
        "DeviceDesc",
        "FriendlyName",
        "Mfg",
        "Service",
        "Class",
        "ClassGUID",
        "Driver",
        "MatchingDeviceId",
        "HardwareID",
        "CompatibleIDs",
        "LocationInformation",
    ):
        parts.append(_query_str(hive, path, name))
    # multi-sz часто в HardwareID через EnumValue
    for name, data, _t in _enum_values(hive, path):
        if name.upper() in {"HARDWAREID", "COMPATIBLEIDS"}:
            if isinstance(data, (list, tuple)):
                parts.extend(str(x) for x in data)
            else:
                parts.append(str(data))
    return " ".join(p for p in parts if p)


def _vid_from_text(text: str) -> str | None:
    m = re.search(r"VID[_\s]?([0-9A-Fa-f]{4})", text)
    return m.group(1).upper() if m else None


def _is_protected(blob: str, key_name: str = "") -> bool:
    text = f"{blob} {key_name}"
    if key_name.upper().startswith("ROOT_HUB"):
        return True
    if PROTECTED_RE.search(text):
        # COMPOSITE PARENT сам по себе не защищает — только вместе с HID
        if re.search(r"COMPOSITE[\s_\-]?PARENT", text, re.I) and not re.search(
            r"CLASS_03|HIDUSB|KEYBOARD|MOUSE|KBDHID|MOUHID", text, re.I
        ):
            return False
        return True
    return False


def _is_target_portable(blob: str, key_name: str = "") -> bool:
    text = f"{blob} {key_name}"
    if TARGET_RE.search(text):
        return True
    vid = _vid_from_text(text)
    if vid and vid in TARGET_VIDS:
        # VID из списка, но не HID/hub
        if not _is_protected(text, key_name):
            return True
    return False


def _force_hklm(path: str, result: CleanResult) -> bool:
    ok, info = force_delete_hklm_tree(path)
    if ok:
        result.deleted_keys.append(path)
        return True
    result.errors.append(f"{path}: {info}")
    return False


def _delete_tree(hive: int, path: str, result: CleanResult) -> None:
    for sub in list(_enum_subkeys(hive, path)):
        _delete_tree(hive, f"{path}\\{sub}", result)

    parent, _, name = path.rpartition("\\")
    if not name:
        result.skipped.append(path)
        return
    try:
        with _open_key(hive, parent, winreg.KEY_ALL_ACCESS) as key:
            winreg.DeleteKey(key, name)
        result.deleted_keys.append(path)
    except FileNotFoundError:
        pass
    except (PermissionError, OSError) as exc:
        if hive == winreg.HKEY_LOCAL_MACHINE:
            if not _force_hklm(path, result):
                result.skipped.append(f"{path} ({exc})")
        else:
            result.errors.append(f"{path}: {exc}")


def _delete_subkeys(hive: int, path: str, result: CleanResult) -> None:
    for sub in list(_enum_subkeys(hive, path)):
        child = f"{path}\\{sub}"
        if hive == winreg.HKEY_LOCAL_MACHINE:
            if path.upper().startswith(r"SYSTEM\CURRENTCONTROLSET\ENUM"):
                if _force_hklm(child, result):
                    continue
        _delete_tree(hive, child, result)


def _subtree_has_protected(hive: int, path: str) -> bool:
    """True, если в дереве есть HID/hub (композит с клавиатурой и т.п.)."""
    blob = _device_blob(hive, path, path)
    if _is_protected(blob, path.rsplit("\\", 1)[-1]):
        return True
    for sub in _enum_subkeys(hive, path):
        if _subtree_has_protected(hive, f"{path}\\{sub}"):
            return True
    return False


def _clear_enum_usb_selective(result: CleanResult, log: Callable[[str], None]) -> None:
    """Enum\\USB: удаляем только портативные цели, сохраняем HID/хабы."""
    root = r"SYSTEM\CurrentControlSet\Enum\USB"
    log(f"Реестр: выборочная очистка {root} (HID/хабы сохранены)")
    for device_id in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root)):
        dpath = f"{root}\\{device_id}"
        if device_id.upper().startswith("ROOT_HUB"):
            result.skipped.append(dpath)
            continue

        # Если любой экземпляр/интерфейс — HID/hub, всё дерево VID&PID оставляем
        if _subtree_has_protected(winreg.HKEY_LOCAL_MACHINE, dpath):
            result.skipped.append(f"{dpath} (protected input/hub)")
            continue

        blob = _device_blob(winreg.HKEY_LOCAL_MACHINE, dpath, device_id)
        # Смотрим экземпляры
        instances = _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, dpath)
        instance_blobs = [blob]
        for inst in instances:
            ipath = f"{dpath}\\{inst}"
            instance_blobs.append(
                _device_blob(winreg.HKEY_LOCAL_MACHINE, ipath, device_id, inst)
            )
            for iface in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, ipath):
                instance_blobs.append(
                    _device_blob(
                        winreg.HKEY_LOCAL_MACHINE,
                        f"{ipath}\\{iface}",
                        device_id,
                        inst,
                        iface,
                    )
                )

        combined = " ".join(instance_blobs)
        if _is_protected(combined, device_id):
            result.skipped.append(f"{dpath} (protected)")
            continue
        if _is_target_portable(combined, device_id):
            if not _force_hklm(dpath, result):
                _delete_tree(winreg.HKEY_LOCAL_MACHINE, dpath, result)
        else:
            # Неизвестное USB-устройство — не трогаем (безопасный режим)
            result.skipped.append(f"{dpath} (kept: not a portable target)")


def _clear_mounted_devices(result: CleanResult) -> None:
    path = r"SYSTEM\MountedDevices"
    for name, data, _rtype in _enum_values(winreg.HKEY_LOCAL_MACHINE, path):
        text = name.upper()
        blob = data if isinstance(data, bytes) else b""
        looks = (
            "USBSTOR" in text
            or "WPD" in text
            or "WPDBUSENUM" in text
            or b"USBSTOR" in blob
            or b"_??_USBSTOR" in blob
            or b"WPDBUSENUM" in blob
            or b"WPD#" in blob
            or b"GARMIN" in blob
            or b"MTP" in blob
        )
        # Не удаляем по голому USB# — могут быть тома, не связанные с чисткой
        if looks:
            try:
                with _open_key(
                    winreg.HKEY_LOCAL_MACHINE, path, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, name)
                result.deleted_values.append(f"{path}\\{name}")
            except OSError as exc:
                result.errors.append(f"{path}\\{name}: {exc}")


def _clear_device_classes(result: CleanResult) -> None:
    base = r"SYSTEM\CurrentControlSet\Control\DeviceClasses"
    for guid in DEVICE_CLASS_GUIDS:
        root = f"{base}\\{guid}"
        for sub in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root)):
            full = f"{root}\\{sub}"
            if _is_protected(sub, sub):
                continue
            if _is_target_portable(sub, sub):
                if not _force_hklm(full, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, full, result)


def _clear_device_containers(result: CleanResult) -> None:
    root = r"SYSTEM\CurrentControlSet\Control\DeviceContainers"
    for container_id in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root)):
        cpath = f"{root}\\{container_id}"
        hint_parts = [container_id]
        for sub in ("BaseContainers", "Properties"):
            sp = f"{cpath}\\{sub}"
            hint_parts.extend(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, sp))
            for name, data, _t in _enum_values(winreg.HKEY_LOCAL_MACHINE, sp):
                hint_parts.append(name)
                if isinstance(data, str):
                    hint_parts.append(data)
                elif isinstance(data, bytes):
                    try:
                        hint_parts.append(data.decode("utf-16-le", errors="ignore"))
                    except Exception:
                        pass
        for sub in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, cpath):
            hint_parts.append(sub)
            for deep in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, f"{cpath}\\{sub}"):
                hint_parts.append(deep)

        combined = " ".join(hint_parts)
        if _is_protected(combined, container_id):
            continue
        if _is_target_portable(combined, container_id):
            if not _force_hklm(cpath, result):
                _delete_tree(winreg.HKEY_LOCAL_MACHINE, cpath, result)


def _clear_vendor_software(result: CleanResult, log: Callable[[str], None]) -> None:
    for path in VENDOR_SOFTWARE_KEYS:
        try:
            with _open_key(winreg.HKEY_LOCAL_MACHINE, path):
                pass
        except FileNotFoundError:
            continue
        except OSError:
            pass
        log(f"Реестр: кэш ПО {path}")
        for sub in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, path):
            child = f"{path}\\{sub}"
            upper = sub.upper()
            wipe = upper in {
                "DEVICES",
                "DEVICE HISTORY",
                "DEVICEHISTORY",
                "PAIRED",
                "HISTORY",
            } or _is_target_portable(sub, sub)
            if wipe or "DEVICE" in upper:
                if not _force_hklm(child, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, child, result)


def clear_bam_traces(result: CleanResult | None = None) -> CleanResult:
    result = result or CleanResult()
    suspicious = (
        "WEVTUTIL",
        "FAST_CLEAR",
        "USBDEVIEW",
        "PRIVAZER",
        "CCLEANER",
        "GARMIN",
        "APPLEMOBILE",
        "ITUNES",
        "ADB.EXE",
        "SIDELOADLY",
        "3UTOOLS",
    )
    for user_sid in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, BAM_PATH):
        path = f"{BAM_PATH}\\{user_sid}"
        for name, _data, _rtype in _enum_values(winreg.HKEY_LOCAL_MACHINE, path):
            upper = name.upper()
            if any(s in upper for s in suspicious):
                try:
                    with _open_key(
                        winreg.HKEY_LOCAL_MACHINE, path, winreg.KEY_SET_VALUE
                    ) as key:
                        winreg.DeleteValue(key, name)
                    result.deleted_values.append(f"{path}\\{name}")
                except OSError as exc:
                    result.errors.append(f"{path}\\{name}: {exc}")
    return result


def _filter_scsi_usbstor(result: CleanResult) -> None:
    root = r"SYSTEM\CurrentControlSet\Enum\SCSI"
    for vendor in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root):
        vpath = f"{root}\\{vendor}"
        upper = vendor.upper()
        if "USB" in upper or "UAS" in upper:
            if not _force_hklm(vpath, result):
                _delete_tree(winreg.HKEY_LOCAL_MACHINE, vpath, result)
            continue
        for inst in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, vpath)):
            ipath = f"{vpath}\\{inst}"
            blob = _device_blob(winreg.HKEY_LOCAL_MACHINE, ipath, vendor, inst)
            if _is_protected(blob, inst):
                continue
            if _is_target_portable(blob, inst) or any(
                x in blob.upper() for x in ("FLASH", "REMOVABLE", "GARMIN")
            ):
                if not _force_hklm(ipath, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, ipath, result)


def _filter_ports_and_modem_class(result: CleanResult) -> None:
    class_guids = (
        "{4d36e96d-e325-11ce-bfc1-08002be10318}",
        "{4d36e978-e325-11ce-bfc1-08002be10318}",
    )
    for guid in class_guids:
        root = rf"SYSTEM\CurrentControlSet\Control\Class\{guid}"
        for sub in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root)):
            if not re.fullmatch(r"\d{4}", sub):
                continue
            ipath = f"{root}\\{sub}"
            blob = _device_blob(winreg.HKEY_LOCAL_MACHINE, ipath, sub)
            if _is_protected(blob, sub):
                continue
            if _is_target_portable(blob, sub):
                if not _force_hklm(ipath, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, ipath, result)


def clean_registry(
    progress: Callable[[str], None] | None = None,
) -> CleanResult:
    """
    Очистка РЕЗИДУАЛЬНЫХ следов флешек/модемов/телефонов/часов.

    ВАЖНО: сами устройства (ветки Enum\\USB, Enum\\USBSTOR, WPDBUSENUM) удаляются
    НЕ здесь, а через pnputil (device_clean) — это безопасно для PnP и не ломает
    подключение новых устройств. Здесь чистятся только сопутствующие артефакты:
    MountedDevices, Portable Devices, EMDMgmt, DeviceClasses, DeviceContainers,
    Class Modem/Ports, кэши ПО, MountPoints2, BAM.
    """
    log = progress or (lambda _m: None)
    result = CleanResult()

    for path in EXTRA_KEYS_HKLM:
        log(f"Реестр: очистка {path}")
        _delete_subkeys(winreg.HKEY_LOCAL_MACHINE, path, result)

    _clear_vendor_software(result, log)

    for path in EXTRA_KEYS_HKCU:
        log(f"Реестр (HKCU): очистка {path}")
        if path.endswith("MountPoints2"):
            for sub in list(_enum_subkeys(winreg.HKEY_CURRENT_USER, path)):
                if sub.startswith("{") or "Volume{" in sub or sub.startswith("##"):
                    if _is_target_portable(sub, sub) or "USBSTOR" in sub.upper():
                        _delete_tree(
                            winreg.HKEY_CURRENT_USER, f"{path}\\{sub}", result
                        )
                    elif "Volume{" in sub or sub.startswith("##"):
                        # том мог быть с флешки — удаляем только явные USBSTOR/WPD
                        pass
        elif path.endswith("KnownDevices"):
            for name, data, _t in list(
                _enum_values(winreg.HKEY_CURRENT_USER, path)
            ):
                blob = f"{name} {data}"
                if _is_protected(blob, name):
                    continue
                if _is_target_portable(blob, name):
                    try:
                        with _open_key(
                            winreg.HKEY_CURRENT_USER, path, winreg.KEY_SET_VALUE
                        ) as key:
                            winreg.DeleteValue(key, name)
                        result.deleted_values.append(f"HKCU\\{path}\\{name}")
                    except OSError as exc:
                        result.errors.append(f"HKCU\\{path}\\{name}: {exc}")
            for sub in list(_enum_subkeys(winreg.HKEY_CURRENT_USER, path)):
                if _is_target_portable(sub, sub) and not _is_protected(sub, sub):
                    _delete_tree(winreg.HKEY_CURRENT_USER, f"{path}\\{sub}", result)

    log("Реестр: MountedDevices (USBSTOR/WPD)")
    _clear_mounted_devices(result)

    log("Реестр: DeviceClasses (портативные, без HID)")
    _clear_device_classes(result)

    log("Реестр: DeviceContainers (портативные, без input)")
    _clear_device_containers(result)

    log("Реестр: Class Modem/Ports (только целевые)")
    _filter_ports_and_modem_class(result)

    log("Реестр: BAM (следы утилит)")
    clear_bam_traces(result)

    return result
