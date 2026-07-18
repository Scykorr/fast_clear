"""Финальный проход: стирание следов самой очистки (без записи Event 104)."""

from __future__ import annotations

from typing import Callable

from fast_clear.eventlog_clean import (
    AUDIT_CHANNELS,
    EventLogResult,
    wipe_logs_via_service,
)
from fast_clear.file_clean import (
    FileCleanResult,
    clear_prefetch,
    clear_powershell_history,
    clear_temp_traces,
)
from fast_clear.registry_clean import CleanResult, clear_bam_traces


def wipe_file_evidence(
    progress: Callable[[str], None] | None = None,
) -> tuple[FileCleanResult, CleanResult]:
    """
    Удаляет НЕ-журнальные артефакты очистки:
    - Prefetch wevtutil / python / powershell / утилит
    - историю PowerShell
    - временные файлы
    - BAM-записи утилит
    Журналы событий чистятся отдельно (через остановку службы), чтобы не оставить
    Event ID 104/1102 «журнал очищен».
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
    return files, bam


def final_log_wipe(
    progress: Callable[[str], None] | None = None,
) -> EventLogResult:
    """
    Финальное стирание журналов аудита через остановку службы EventLog.
    Не оставляет Event ID 104/1102 (в отличие от wevtutil cl).
    """
    return wipe_logs_via_service(AUDIT_CHANNELS, progress=progress)
