"""Общий сценарий очистки для CLI и GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fast_clear.admin import enable_cleanup_privileges, is_admin
from fast_clear.eventlog_clean import EventLogResult, clear_event_logs
from fast_clear.file_clean import FileCleanResult, clear_setupapi_logs
from fast_clear.registry_clean import CleanResult, clean_registry
from fast_clear.self_clean import final_quiet_pass, wipe_cleanup_evidence

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

    if opts.do_registry:
        log("=== Реестр ===")
        summary.registry = clean_registry(progress=log)

    if opts.do_eventlogs:
        log("=== Журналы событий ===")
        summary.eventlogs = clear_event_logs(progress=log)

    if opts.do_files:
        log("=== Файлы SetupAPI ===")
        summary.files = clear_setupapi_logs(progress=log)

    if opts.do_self_clean:
        log("=== Самоочистка следов ===")
        summary.self_logs, summary.self_files, summary.self_bam = (
            wipe_cleanup_evidence(progress=log)
        )
        final_quiet_pass(progress=log)

    log("Готово.")
    return summary


def format_summary(summary: CleanupSummary) -> str:
    """Текстовый итог для лога / CLI."""
    if summary.error:
        return f"Ошибка: {summary.error}"

    lines: list[str] = ["--- Итог ---"]
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
