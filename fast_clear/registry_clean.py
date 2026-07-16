"""Очистка реестра от истории USB / MTP / модемов / телефонов / часов."""

from __future__ import annotations

import re
import winreg
from dataclasses import dataclass, field
from typing import Callable

from fast_clear.reg_acl import force_delete_hklm_tree

# GUID классов: накопители, USB, модемы, COM-порты, WPD/MTP, сети (USB-модемы)
DEVICE_CLASS_GUIDS = (
    "{53f56307-b6bf-11d0-94f2-00a0c91efb8b}",  # Disk
    "{53f5630d-b6bf-11d0-94f2-00a0c91efb8b}",  # Volume
    "{a5dcbf10-6530-11d2-901f-00c04fb951ed}",  # USB device interface
    "{f18a0e88-c30c-11d0-8815-00a0c906bed8}",  # USB hub
    "{4d36e96d-e325-11ce-bfc1-08002be10318}",  # Modem
    "{4d36e978-e325-11ce-bfc1-08002be10318}",  # Ports (COM/LPT)
    "{4d36e972-e325-11ce-bfc1-08002be10318}",  # Net (USB tethering / WWAN)
    "{eec5ad98-8080-425f-922a-dabf3de3f69a}",  # WPD
    "{6ac27878-a6bc-11d0-96b8-00a0c91ede8a}",  # WPD (alt)
    "{6bdd1fc6-810f-11d0-bec7-08002be2092f}",  # StillImage / WIA (часть телефонов)
    "{50dd5230-ba8a-11d1-bf5d-0000f805f530}",  # SmartCardReader (USB CCID / часы)
)

# Полная очистка деревьев Enum (история PnP)
ENUM_USB_ROOTS = (
    r"SYSTEM\CurrentControlSet\Enum\USBSTOR",
    r"SYSTEM\CurrentControlSet\Enum\USB",
    r"SYSTEM\CurrentControlSet\Enum\USBPRINT",
    r"SYSTEM\CurrentControlSet\Enum\WPD",
    r"SYSTEM\CurrentControlSet\Enum\SCSI",
    r"SYSTEM\CurrentControlSet\Enum\SWD\WPDBUSENUM",
    r"SYSTEM\CurrentControlSet\Enum\Modem",  # USB/serial модемы → COM
    r"SYSTEM\CurrentControlSet\Enum\UMB",  # User-Mode Bus (MTP и др.)
    r"SYSTEM\CurrentControlSet\Enum\SWD\MSMMB",  # Mobile Broadband
)

EXTRA_KEYS_HKLM = (
    r"SOFTWARE\Microsoft\Windows Portable Devices\Devices",
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\EMDMgmt",
    r"SYSTEM\CurrentControlSet\Control\usbflags",
    r"SYSTEM\CurrentControlSet\Services\USBSTOR\Enum",
    r"SYSTEM\CurrentControlSet\Services\Wudfrd\Enum",
    r"SYSTEM\CurrentControlSet\Services\Modem\Enum",
    r"SYSTEM\CurrentControlSet\Services\usbser\Enum",
    r"SYSTEM\CurrentControlSet\Services\Usbccgp\Enum",
    r"SYSTEM\CurrentControlSet\Services\WUDFWpdFs\Enum",
    r"SYSTEM\CurrentControlSet\Services\WpdUpFltr\Enum",
    r"SYSTEM\CurrentControlSet\Services\WudfUsbccidDriver\Enum",
    r"SYSTEM\CurrentControlSet\Services\WinUsb\Enum",
    r"SYSTEM\CurrentControlSet\Services\usbchipidea\Enum",
    r"SYSTEM\CurrentControlSet\Services\WWANSvc\Enum",
)

# Кэши ПО производителей (история подключённых устройств)
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

# Признаки портативных / модемных / телефонных / «часовых» устройств в путях и описаниях
PORTABLE_HINT_RE = re.compile(
    r"("
    r"USB|USBSTOR|WPDBUSENUM|VID_|PID_|MTP|WPD|MODEM|WWAN|MBB|"
    r"GARMIN|APPLE|IPHONE|IPAD|IPOD|ANDROID|SAMSUNG|XIAOMI|HUAWEI|"
    r"ONEPLUS|PIXEL|SONY|NOKIA|MOTOROLA|OPPO|VIVO|REALME|"
    r"MOBILE|PHONE|HANDHELD|COMPOSITE|RNDIS|CDC_ACM|CDC_NCM|QMI|MBIM|"
    r"SERIAL|USBSER|WINUSB|TETHER|HOTSPOT|"
    r"USB#|SWD#|WPD#"
    r")",
    re.IGNORECASE,
)

USB_INSTANCE_RE = PORTABLE_HINT_RE


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


def _looks_portable(*parts: str) -> bool:
    blob = " ".join(p for p in parts if p)
    return bool(PORTABLE_HINT_RE.search(blob))


def _force_hklm(path: str, result: CleanResult) -> bool:
    ok, info = force_delete_hklm_tree(path)
    if ok:
        result.deleted_keys.append(path)
        return True
    result.errors.append(f"{path}: {info}")
    return False


def _delete_tree(hive: int, path: str, result: CleanResult) -> None:
    """Рекурсивно удаляет ключ реестра."""
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
    """Удаляет все дочерние ключи, оставляя сам корень."""
    for sub in list(_enum_subkeys(hive, path)):
        child = f"{path}\\{sub}"
        if hive == winreg.HKEY_LOCAL_MACHINE:
            if path.upper().startswith(r"SYSTEM\CURRENTCONTROLSET\ENUM"):
                if _force_hklm(child, result):
                    continue
        _delete_tree(hive, child, result)


def _clear_mounted_devices(result: CleanResult) -> None:
    """Удаляет MountedDevices, связанные с USB / WPD / MTP."""
    path = r"SYSTEM\MountedDevices"
    for name, data, _rtype in _enum_values(winreg.HKEY_LOCAL_MACHINE, path):
        text = name.upper()
        blob = data if isinstance(data, bytes) else b""
        looks = (
            "USBSTOR" in text
            or "USB#" in text
            or "WPD" in text
            or "WPDBUSENUM" in text
            or "SWD#" in text
            or b"USBSTOR" in blob
            or b"USB#" in blob
            or b"_??_USBSTOR" in blob
            or b"WPDBUSENUM" in blob
            or b"WPD#" in blob
            or b"SWD#" in blob
            or b"GARMIN" in blob
            or b"MTP" in blob
        )
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
            if USB_INSTANCE_RE.search(sub):
                if not _force_hklm(full, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, full, result)


def _clear_device_containers(result: CleanResult) -> None:
    """Удаляет контейнеры устройств с признаками USB/телефона/модема/часов."""
    root = r"SYSTEM\CurrentControlSet\Control\DeviceContainers"
    for container_id in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root)):
        cpath = f"{root}\\{container_id}"
        # BaseContainers / Properties часто содержат имена устройств
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
        # Также смотрим дочерние GUID устройств
        for sub in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, cpath):
            hint_parts.append(sub)
            for deep in _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, f"{cpath}\\{sub}"):
                hint_parts.append(deep)

        if _looks_portable(*hint_parts):
            if not _force_hklm(cpath, result):
                _delete_tree(winreg.HKEY_LOCAL_MACHINE, cpath, result)


def _clear_vendor_software(result: CleanResult, log: Callable[[str], None]) -> None:
    """Чистит кэши Apple/Garmin/Samsung и т.п., связанные с устройствами."""
    for path in VENDOR_SOFTWARE_KEYS:
        if not _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, path) and not _enum_values(
            winreg.HKEY_LOCAL_MACHINE, path
        ):
            # ключ может существовать пустым или отсутствовать
            try:
                with _open_key(winreg.HKEY_LOCAL_MACHINE, path):
                    pass
            except FileNotFoundError:
                continue
            except OSError:
                pass
        log(f"Реестр: кэш ПО {path}")
        # Удаляем подключи с намёком на устройства; если корень «история» — целиком
        subs = _enum_subkeys(winreg.HKEY_LOCAL_MACHINE, path)
        if not subs:
            # значения на корне
            for name, _d, _t in list(_enum_values(winreg.HKEY_LOCAL_MACHINE, path)):
                if _looks_portable(name, path):
                    try:
                        with _open_key(
                            winreg.HKEY_LOCAL_MACHINE, path, winreg.KEY_SET_VALUE
                        ) as key:
                            winreg.DeleteValue(key, name)
                        result.deleted_values.append(f"{path}\\{name}")
                    except OSError as exc:
                        result.errors.append(f"{path}\\{name}: {exc}")
            continue

        for sub in subs:
            child = f"{path}\\{sub}"
            upper = sub.upper()
            # Типичные ветки истории устройств / paired devices
            wipe_all = upper in {
                "DEVICES",
                "DEVICE HISTORY",
                "DEVICEHISTORY",
                "PAIRED",
                "HISTORY",
                "COMMON",
                "MOBILE DEVICE",
            } or _looks_portable(sub)
            if wipe_all or "DEVICE" in upper or "USB" in upper:
                if not _force_hklm(child, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, child, result)


def clear_bam_traces(result: CleanResult | None = None) -> CleanResult:
    """Удаляет из BAM записи утилит очистки и типичных USB/MTP-клиентов."""
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
        "SAMSUNG",
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
    """В Enum\\SCSI удаляет узлы USB/UAS и портативных накопителей."""
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
            desc = _query_str(winreg.HKEY_LOCAL_MACHINE, ipath, "DeviceDesc")
            mfg = _query_str(winreg.HKEY_LOCAL_MACHINE, ipath, "Mfg")
            if _looks_portable(desc, mfg, inst, vendor) or any(
                x in f"{desc} {mfg}".upper()
                for x in ("FLASH", "REMOVABLE", "PHONE", "GARMIN")
            ):
                if not _force_hklm(ipath, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, ipath, result)


def _filter_ports_and_modem_class(result: CleanResult) -> None:
    """
    Control\\Class\\{Modem} и {Ports}: удаляет экземпляры с USB/телефон/модем.
    """
    class_guids = (
        "{4d36e96d-e325-11ce-bfc1-08002be10318}",  # Modem
        "{4d36e978-e325-11ce-bfc1-08002be10318}",  # Ports
    )
    for guid in class_guids:
        root = rf"SYSTEM\CurrentControlSet\Control\Class\{guid}"
        for sub in list(_enum_subkeys(winreg.HKEY_LOCAL_MACHINE, root)):
            if not re.fullmatch(r"\d{4}", sub):
                continue
            ipath = f"{root}\\{sub}"
            desc = _query_str(winreg.HKEY_LOCAL_MACHINE, ipath, "DriverDesc")
            matching = _query_str(winreg.HKEY_LOCAL_MACHINE, ipath, "MatchingDeviceId")
            provider = _query_str(winreg.HKEY_LOCAL_MACHINE, ipath, "ProviderName")
            if _looks_portable(desc, matching, provider, sub):
                if not _force_hklm(ipath, result):
                    _delete_tree(winreg.HKEY_LOCAL_MACHINE, ipath, result)


def clean_registry(
    progress: Callable[[str], None] | None = None,
) -> CleanResult:
    """Очистка реестра: флешки, модемы, телефоны, часы (Garmin и др.)."""
    log = progress or (lambda _m: None)
    result = CleanResult()

    for path in ENUM_USB_ROOTS:
        if path.endswith(r"\SCSI"):
            log(f"Реестр: фильтрация {path}")
            _filter_scsi_usbstor(result)
            continue
        log(f"Реестр: очистка {path}")
        _delete_subkeys(winreg.HKEY_LOCAL_MACHINE, path, result)

    for path in EXTRA_KEYS_HKLM:
        log(f"Реестр: очистка {path}")
        _delete_subkeys(winreg.HKEY_LOCAL_MACHINE, path, result)

    _clear_vendor_software(result, log)

    for path in EXTRA_KEYS_HKCU:
        log(f"Реестр (HKCU): очистка {path}")
        if path.endswith("MountPoints2"):
            for sub in list(_enum_subkeys(winreg.HKEY_CURRENT_USER, path)):
                if (
                    sub.startswith("{")
                    or "Volume{" in sub
                    or sub.startswith("##")
                    or _looks_portable(sub)
                ):
                    _delete_tree(winreg.HKEY_CURRENT_USER, f"{path}\\{sub}", result)
        elif path.endswith("KnownDevices"):
            _delete_subkeys(winreg.HKEY_CURRENT_USER, path, result)
            # значения на корне KnownDevices
            for name, _d, _t in list(
                _enum_values(winreg.HKEY_CURRENT_USER, path)
            ):
                try:
                    with _open_key(
                        winreg.HKEY_CURRENT_USER, path, winreg.KEY_SET_VALUE
                    ) as key:
                        winreg.DeleteValue(key, name)
                    result.deleted_values.append(f"HKCU\\{path}\\{name}")
                except OSError as exc:
                    result.errors.append(f"HKCU\\{path}\\{name}: {exc}")
        else:
            _delete_subkeys(winreg.HKEY_CURRENT_USER, path, result)

    log("Реестр: MountedDevices (USB/WPD)")
    _clear_mounted_devices(result)

    log("Реестр: DeviceClasses (USB/модем/WPD)")
    _clear_device_classes(result)

    log("Реестр: DeviceContainers (портативные)")
    _clear_device_containers(result)

    log("Реестр: Class Modem/Ports (USB)")
    _filter_ports_and_modem_class(result)

    log("Реестр: BAM (следы утилит)")
    clear_bam_traces(result)

    return result
