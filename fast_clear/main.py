"""Точка входа CLI / GUI: python -m fast_clear"""

from __future__ import annotations

import argparse
import sys

from fast_clear import __version__
from fast_clear.admin import require_admin
from fast_clear.cleanup import CleanupOptions, format_summary, run_cleanup


def _ts_print(msg: str) -> None:
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fast_clear",
        description=(
            "Очистка следов USB-устройств в реестре, журналах событий и файлах "
            "Windows 10/11, включая следы самой очистки."
        ),
    )
    p.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"fast_clear {__version__}",
    )
    p.add_argument(
        "--gui",
        action="store_true",
        help="Запустить графический интерфейс",
    )
    p.add_argument(
        "--cli",
        action="store_true",
        help="Запустить в режиме командной строки (без GUI)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать план действий, ничего не изменять",
    )
    p.add_argument(
        "--skip-registry",
        action="store_true",
        help="Не трогать реестр",
    )
    p.add_argument(
        "--skip-eventlogs",
        action="store_true",
        help="Не очищать журналы событий",
    )
    p.add_argument(
        "--skip-files",
        action="store_true",
        help="Не очищать SetupAPI / Prefetch / историю",
    )
    p.add_argument(
        "--skip-self-clean",
        action="store_true",
        help="Не выполнять финальную самоочистку следов",
    )
    p.add_argument(
        "--repair",
        "--repair-input",
        dest="repair_input",
        action="store_true",
        help="Восстановить USB (клавиатура/мышь/флешки), без очистки",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Минимальный вывод",
    )
    return p


def print_plan() -> None:
    print(f"fast_clear {__version__} — план (dry-run)\n")
    print("1. Устройства: pnputil /remove-device для phantom-накопителей/")
    print("   телефонов/часов/модемов (клав., мыши, HID, USB-хабы НЕ трогаются)")
    print("2. Реестр: MountedDevices, Portable Devices, EMDMgmt, DeviceClasses,")
    print("   DeviceContainers, Class Modem/Ports, кэши ПО, MountPoints2, BAM")
    print("3. Файлы: setupapi.* (+ротация), Amcache, Prefetch утилит, PS history")
    print("4. Журналы: стирание через остановку службы EventLog (без Event 104)")
    print("\nТребуются права администратора. Изменения не выполняются (--dry-run).")


def should_use_gui(args: argparse.Namespace) -> bool:
    if args.cli or args.dry_run or args.repair_input:
        return False
    if args.gui:
        return True
    if getattr(sys, "frozen", False):
        return True
    return not any(
        (
            args.skip_registry,
            args.skip_eventlogs,
            args.skip_files,
            args.skip_self_clean,
            args.quiet,
        )
    ) and len(sys.argv) <= 1


def run_cli(args: argparse.Namespace) -> int:
    if args.dry_run:
        print_plan()
        return 0

    require_admin()
    progress = (lambda _m: None) if args.quiet else _ts_print

    print(f"fast_clear {__version__}")

    if args.repair_input:
        from fast_clear.repair import repair_usb

        repair_usb(progress=progress)
        return 0

    opts = CleanupOptions(
        do_registry=not args.skip_registry,
        do_eventlogs=not args.skip_eventlogs,
        do_files=not args.skip_files,
        do_self_clean=not args.skip_self_clean,
    )
    summary = run_cleanup(options=opts, progress=progress)
    if not args.quiet:
        print()
        print(format_summary(summary))
    return 1 if summary.error else 0


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    if should_use_gui(args):
        from fast_clear.gui import run_gui

        return run_gui()

    return run_cli(args)


def main() -> None:
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\nПрервано.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
