"""Общий сценарий очистки для CLI и GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fast_clear.admin import enable_cleanup_privileges, is_admin
from fast_clear.device_clean import DeviceCleanResult, clean_device_history
from fast_clear.eventlog_clean import EventLogResult, wipe_logs_via_service
from fast_clear.file_clean import FileCleanResult, clear_setupapi_logs
from fast_clear.registry_clean import CleanResult, clean_registry
from fast_clear.self_clean import final_log_wipe, wipe_file_evidence

ProgressCb = Callable[[str], None]


@dataclass
class CleanupOptions:
    do_registry: bool = True
    do_eventlogs: bool = True
    do_files: bool = True
    do_self_clean: bool = True


@dataclass
class CleanupSummary:
    privileges: list[str] = field(default_factory=list)
    devices: DeviceCleanResult | None = None
    registry: CleanResult | None = None
    eventlogs: EventLogResult | None = None
    files: FileCleanResult | None = None
    self_logs: EventLogResult | None = None
    self_files: FileCleanResult | None = None
    self_bam: CleanResult | None = None
    error: str | None = None


def run_cleanup(
    options: CleanupOptions | None = None,
    progress: ProgressCb | None = None,
) -> CleanupSummary:
    """Выполняет очистку. Требует права администратора."""
    opts = options or CleanupOptions()
    log = progress or (lambda _m: None)
    summary = CleanupSummary()

    if not is_admin():
        summary.error = "Требуются права администратора"
        return summary

    summary.privileges = enable_cleanup_privileges()
    log(
        "Привилегии: "
        + (
            ", ".join(summary.privileges)
            if summary.privileges
            else "не удалось включить дополнительные"
        )
    )

    # 1) Устройства и реестр (генерируют PnP-события — их сотрём в конце)
    if opts.do_registry:
        log("=== Устройства (pnputil) ===")
        summary.devices = clean_device_history(progress=log)
        log("=== Реестр ===")
        summary.registry = clean_registry(progress=log)

    # 2) Файлы SetupAPI / Amcache
    if opts.do_files:
        log("=== Файлы SetupAPI / Amcache ===")
        summary.files = clear_setupapi_logs(progress=log)

    # 3) Самоочистка не-журнальных следов (Prefetch, история, BAM)
    if opts.do_self_clean:
        log("=== Самоочистка следов (файлы) ===")
        summary.self_files, summary.self_bam = wipe_file_evidence(progress=log)

    # 4) ПОСЛЕДНИМ — журналы событий через остановку службы (без Event 104).
    #    Делается в самом конце, чтобы стереть и события от шагов выше.
    if opts.do_eventlogs or opts.do_self_clean:
        log("=== Журналы событий (стирание без следа очистки) ===")
        summary.eventlogs = wipe_logs_via_service(progress=log)
        summary.self_logs = summary.eventlogs

    log("Готово.")
    return summary


def format_summary(summary: CleanupSummary) -> str:
    """Текстовый итог для лога / CLI."""
    if summary.error:
        return f"Ошибка: {summary.error}"

    lines: list[str] = ["--- Итог ---"]
    if summary.devices is not None:
        d = summary.devices
        lines.append(
            f"Устройства (phantom): удалено={len(d.removed)}, "
            f"пропущено={len(d.skipped)}, ошибок={len(d.errors)}"
        )
        for err in d.errors[:8]:
            lines.append(f"  ! {err}")
    if summary.registry is not None:
        r = summary.registry
        lines.append(
            f"Реестр: ключей={len(r.deleted_keys)}, "
            f"значений={len(r.deleted_values)}, "
            f"пропущено={len(r.skipped)}, ошибок={len(r.errors)}"
        )
        for err in r.errors[:12]:
            lines.append(f"  ! {err}")
        if len(r.errors) > 12:
            lines.append(f"  … ещё {len(r.errors) - 12}")

    if summary.eventlogs is not None:
        e = summary.eventlogs
        lines.append(
            f"Журналы: очищено={len(e.cleared)}, "
            f"нет канала={len(e.missing)}, ошибок={len(e.failed)}"
        )
        for err in e.failed[:8]:
            lines.append(f"  ! {err}")

    if summary.files is not None:
        f = summary.files
        lines.append(
            f"SetupAPI: обнулено={len(f.truncated)}, ошибок={len(f.errors)}"
        )

    if summary.self_logs is not None:
        lines.append(f"Самоочистка журналов: каналов={len(summary.self_logs.cleared)}")
    if summary.self_files is not None:
        sf = summary.self_files
        lines.append(
            f"Самоочистка файлов: удалено={len(sf.deleted)}, "
            f"обнулено={len(sf.truncated)}"
        )
    if summary.self_bam is not None:
        lines.append(f"BAM: значений={len(summary.self_bam.deleted_values)}")

    return "\n".join(lines)
