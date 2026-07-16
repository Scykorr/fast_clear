"""Проверка прав администратора и включение привилегий."""

from __future__ import annotations

import ctypes
import sys

from fast_clear.reg_acl import ensure_privileges


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def require_admin() -> None:
    if not is_admin():
        print(
            "Ошибка: требуются права администратора.\n"
            "Запустите: правый клик → «Запуск от имени администратора»\n"
            "или: Start-Process python -ArgumentList '-m fast_clear' -Verb RunAs",
            file=sys.stderr,
        )
        sys.exit(1)


def enable_cleanup_privileges() -> list[str]:
    """Включает привилегии, нужные для удаления защищённых ключей и логов."""
    return ensure_privileges()
