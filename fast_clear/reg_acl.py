"""Смена владельца и ACL защищённых ключей реестра через SetNamedSecurityInfo."""

from __future__ import annotations

import ctypes
import subprocess
import winreg
from ctypes import wintypes

advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

SE_REGISTRY_KEY = 4
OWNER_SECURITY_INFORMATION = 0x00000001
DACL_SECURITY_INFORMATION = 0x00000004

TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x00000002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WinBuiltinAdministratorsSid = 26

KEY_ALL_ACCESS = 0xF003F
REG_OPTION_BACKUP_RESTORE = 0x00000004
TRUSTEE_IS_SID = 0
TRUSTEE_IS_GROUP = 2
SET_ACCESS = 1
SUB_CONTAINERS_AND_OBJECTS_INHERIT = 0x3
NO_MULTIPLE_TRUSTEE = 0

_PRIVILEGES_READY = False


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [
        ("PrivilegeCount", wintypes.DWORD),
        ("Privileges", LUID_AND_ATTRIBUTES * 1),
    ]


class TRUSTEE_W(ctypes.Structure):
    _fields_ = [
        ("pMultipleTrustee", ctypes.c_void_p),
        ("MultipleTrusteeOperation", ctypes.c_int),
        ("TrusteeForm", ctypes.c_int),
        ("TrusteeType", ctypes.c_int),
        ("ptstrName", ctypes.c_void_p),
    ]


class EXPLICIT_ACCESS_W(ctypes.Structure):
    _fields_ = [
        ("grfAccessPermissions", wintypes.DWORD),
        ("grfAccessMode", ctypes.c_int),
        ("grfInheritance", wintypes.DWORD),
        ("Trustee", TRUSTEE_W),
    ]


advapi32.SetNamedSecurityInfoW.argtypes = [
    wintypes.LPWSTR,
    ctypes.c_uint,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

advapi32.SetEntriesInAclW.argtypes = [
    wintypes.ULONG,
    ctypes.POINTER(EXPLICIT_ACCESS_W),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
advapi32.SetEntriesInAclW.restype = wintypes.DWORD


def _enable_priv(name: str) -> bool:
    """Включает привилегию. OpenProcessToken(GetCurrentProcess) на части сборок даёт ERROR_INVALID_HANDLE."""
    pid = kernel32.GetCurrentProcessId()
    h_proc = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid,
    )
    if not h_proc:
        h_proc = kernel32.GetCurrentProcess()

    h_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        h_proc,
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(h_token),
    ):
        if h_proc and h_proc != kernel32.GetCurrentProcess():
            kernel32.CloseHandle(h_proc)
        return False

    try:
        luid = LUID()
        if not advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES()
        tp.PrivilegeCount = 1
        tp.Privileges[0].Luid = luid
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        ctypes.set_last_error(0)
        advapi32.AdjustTokenPrivileges(
            h_token, False, ctypes.byref(tp), 0, None, None
        )
        return ctypes.get_last_error() == 0
    finally:
        kernel32.CloseHandle(h_token)
        if h_proc and h_proc != -1 and h_proc != kernel32.GetCurrentProcess():
            kernel32.CloseHandle(h_proc)


def ensure_privileges() -> list[str]:
    global _PRIVILEGES_READY
    names = (
        "SeTakeOwnershipPrivilege",
        "SeBackupPrivilege",
        "SeRestorePrivilege",
        "SeSecurityPrivilege",
    )
    enabled = [n for n in names if _enable_priv(n)]
    _PRIVILEGES_READY = bool(enabled)
    return enabled


def _admin_sid_buffer():
    size = wintypes.DWORD(0)
    advapi32.CreateWellKnownSid(
        WinBuiltinAdministratorsSid, None, None, ctypes.byref(size)
    )
    buf = (ctypes.c_char * max(size.value, 64))()
    if not advapi32.CreateWellKnownSid(
        WinBuiltinAdministratorsSid, None, buf, ctypes.byref(size)
    ):
        raise OSError(ctypes.get_last_error(), "CreateWellKnownSid")
    return buf


def named_path(key_path: str) -> str:
    p = key_path.replace("/", "\\").lstrip("\\")
    while "\\\\" in p:
        p = p.replace("\\\\", "\\")
    if p.upper().startswith("MACHINE\\"):
        return p
    return "MACHINE\\" + p


def unlock_key(key_path: str) -> tuple[bool, int, int]:
    if not _PRIVILEGES_READY:
        ensure_privileges()

    sid_buf = _admin_sid_buffer()
    sid = ctypes.cast(sid_buf, ctypes.c_void_p)
    path = named_path(key_path)

    rc_owner = advapi32.SetNamedSecurityInfoW(
        path,
        SE_REGISTRY_KEY,
        OWNER_SECURITY_INFORMATION,
        sid,
        None,
        None,
        None,
    )

    ea = EXPLICIT_ACCESS_W()
    ea.grfAccessPermissions = KEY_ALL_ACCESS
    ea.grfAccessMode = SET_ACCESS
    ea.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT
    ea.Trustee.pMultipleTrustee = None
    ea.Trustee.MultipleTrusteeOperation = NO_MULTIPLE_TRUSTEE
    ea.Trustee.TrusteeForm = TRUSTEE_IS_SID
    ea.Trustee.TrusteeType = TRUSTEE_IS_GROUP
    ea.Trustee.ptstrName = sid

    new_dacl = ctypes.c_void_p()
    acl_err = advapi32.SetEntriesInAclW(
        1, ctypes.byref(ea), None, ctypes.byref(new_dacl)
    )
    if acl_err != 0:
        return False, rc_owner, acl_err

    try:
        rc_dacl = advapi32.SetNamedSecurityInfoW(
            path,
            SE_REGISTRY_KEY,
            DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION,
            sid,
            None,
            new_dacl,
            None,
        )
    finally:
        if new_dacl:
            kernel32.LocalFree(new_dacl)

    return (rc_owner == 0 and rc_dacl == 0), rc_owner, rc_dacl


def _open(path: str, access: int = winreg.KEY_READ):
    """Открывает ключ; при отказе — с REG_OPTION_BACKUP_RESTORE."""
    flags = access | winreg.KEY_WOW64_64KEY
    try:
        return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, flags)
    except OSError:
        return winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, path, REG_OPTION_BACKUP_RESTORE, flags
        )


def _enum_subkeys(path: str) -> list[str]:
    try:
        with _open(path, winreg.KEY_READ) as key:
            out: list[str] = []
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
            return out
    except OSError:
        return []


def _exists(path: str) -> bool:
    try:
        with _open(path, winreg.KEY_READ):
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _clear_values(path: str) -> None:
    try:
        with _open(path, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    name, _val, _typ = winreg.EnumValue(key, 0)
                    winreg.DeleteValue(key, name)
                except OSError:
                    break
    except OSError:
        pass


def _delete_one(path: str) -> bool:
    parent, _, name = path.rpartition("\\")
    if not name:
        return False
    _clear_values(path)
    try:
        with _open(parent, winreg.KEY_ALL_ACCESS) as key:
            winreg.DeleteKey(key, name)
        return not _exists(path)
    except FileNotFoundError:
        return True
    except OSError:
        proc = subprocess.run(
            ["reg.exe", "delete", rf"HKLM\{path}", "/f"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc.returncode == 0 and not _exists(path)


def force_delete_hklm_tree(key_path: str) -> tuple[bool, str]:
    """Принудительно удаляет дерево HKLM\\key_path (включая Properties)."""
    key_path = key_path.replace("/", "\\").lstrip("\\")
    while "\\\\" in key_path:
        key_path = key_path.replace("\\\\", "\\")

    ensure_privileges()

    if not _exists(key_path):
        return True, "missing"

    errors: list[str] = []

    def walk_delete(p: str) -> None:
        # Сначала снимаем ACL — иначе дочерние Properties не видны
        ok, rc_o, rc_d = unlock_key(p)
        for sub in list(_enum_subkeys(p)):
            walk_delete(f"{p}\\{sub}")
        if not _delete_one(p):
            # повторный unlock + delete
            unlock_key(p)
            if not _delete_one(p):
                errors.append(f"{p} (owner={rc_o}, dacl={rc_d})")

    walk_delete(key_path)

    if not _exists(key_path):
        return True, "ok"
    return False, "; ".join(errors[:8]) or "still exists"
