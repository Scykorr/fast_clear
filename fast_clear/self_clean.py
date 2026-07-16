"""Финальный проход: стирание следов самой очистки."""

from __future__ import annotations

from typing import Callable

from fast_clear.eventlog_clean import EventLogResult, clear_audit_traces, clear_event_logs
from fast_clear.file_clean import (
    FileCleanResult,
    clear_prefetch,
    clear_powershell_history,
    clear_temp_traces,
)
from fast_clear.registry_clean import CleanResult, clear_bam_traces


def wipe_cleanup_evidence(
    progress: Callable[[str], None] | None = None,
) -> tuple[EventLogResult, FileCleanResult, CleanResult]:
    """
    Удаляет артефакты, которые появляются *из-за* очистки:
    - записи «журнал очищен» (повторный clear System/Security/Eventlog)
    - Prefetch wevtutil/python/powershell
    - историю PowerShell
    - BAM-записи утилит
    - временные файлы
    """
    log = progress or (lambda _m: None)

    log("Самоочистка: Prefetch / история / temp")
    files = FileCleanResult()
    for part in (
        clear_prefetch(progress=progress),
        clear_powershell_history(progress=progress),
        clear_temp_traces(progress=progress),
    ):
        files.truncated.extend(part.truncated)
        files.deleted.extend(part.deleted)
        files.errors.extend(part.errors)

    log("Самоочистка: BAM")
    bam = clear_bam_traces()

    # Два прохода: первый снимает 104/1102 от USB-журналов,
    # второй — от очистки самих audit-каналов.
    log("Самоочистка: журналы аудита (проход 1)")
    logs1 = clear_audit_traces(progress=progress)
    log("Самоочистка: журналы аудита (проход 2)")
    logs2 = clear_audit_traces(progress=progress)
    logs1.cleared.extend(logs2.cleared)
    logs1.failed.extend(logs2.failed)
    logs1.missing.extend(logs2.missing)

    # Prefetch wevtutil мог появиться снова после cl
    log("Самоочистка: Prefetch (повтор)")
    pf = clear_prefetch(progress=progress)
    files.deleted.extend(pf.deleted)
    files.errors.extend(pf.errors)

    return logs1, files, bam


def final_quiet_pass(progress: Callable[[str], None] | None = None) -> None:
    """Тихий финальный clear только audit-каналов без лишнего шума в выводе."""
    clear_event_logs(
        (
            "System",
            "Security",
            "Microsoft-Windows-Eventlog/Operational",
        ),
        progress=progress,
    )
    clear_prefetch(progress=progress)
