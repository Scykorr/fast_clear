"""fast_clear — очистка следов USB-устройств в Windows 10/11."""

from __future__ import annotations

import sys
from pathlib import Path


def _version_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    paths = [
        here.parent / "VERSION",
        here / "VERSION",
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.insert(0, Path(meipass) / "VERSION")
        paths.insert(0, Path(sys.executable).resolve().parent / "VERSION")
    return paths


def _read_version() -> str:
    for path in _version_candidates():
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return "0.0.0"


__version__ = _read_version()
__version_info__ = tuple(int(x) for x in __version__.split("."))

__all__ = ["__version__", "__version_info__"]
