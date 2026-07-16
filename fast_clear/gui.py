"""Графический интерфейс fast_clear (tkinter)."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk

from fast_clear import __version__
from fast_clear.admin import is_admin
from fast_clear.cleanup import CleanupOptions, format_summary, run_cleanup


def _ts() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")


def relaunch_as_admin() -> bool:
    """Перезапускает текущий процесс с UAC. True если запрос отправлен."""
    import ctypes

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        executable = sys.executable
        script = sys.argv[0]
        rest = " ".join(f'"{a}"' for a in sys.argv[1:])
        params = f'"{script}" {rest}'.strip()

    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, params, None, 1
    )
    return rc > 32


class FastClearApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"fast_clear {__version__}")
        self.minsize(640, 480)
        self.geometry("720x560")
        self.configure(bg="#1e1e1e")

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._finish_ok: bool | None = None

        self._build_style()
        self._build_ui()
        self._refresh_admin_status()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabelframe", background="#1e1e1e", foreground="#e0e0e0")
        style.configure(
            "TLabelframe.Label", background="#1e1e1e", foreground="#e0e0e0"
        )
        style.configure("TLabel", background="#1e1e1e", foreground="#e0e0e0")
        style.configure("TCheckbutton", background="#1e1e1e", foreground="#e0e0e0")
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="fast_clear", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(
            root,
            text=(
                f"v{__version__} — очистка следов USB в реестре, журналах и файлах "
                "Windows 10/11"
            ),
            style="Status.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))

        self.admin_var = tk.StringVar(value="")
        ttk.Label(
            root, textvariable=self.admin_var, style="Status.TLabel"
        ).pack(anchor=tk.W, pady=(0, 8))

        opts = ttk.LabelFrame(root, text="Что очищать", padding=10)
        opts.pack(fill=tk.X, pady=(0, 12))

        self.var_registry = tk.BooleanVar(value=True)
        self.var_eventlogs = tk.BooleanVar(value=True)
        self.var_files = tk.BooleanVar(value=True)
        self.var_self = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            opts,
            text="Реестр (флешки, модемы, телефоны, часы/Garmin, WPD/MTP…)",
            variable=self.var_registry,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            opts,
            text="Журналы событий (PnP/USB/WPD/WWAN + System/Security)",
            variable=self.var_eventlogs,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            opts, text="Файлы SetupAPI", variable=self.var_files
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            opts, text="Самоочистка следов очистки", variable=self.var_self
        ).pack(anchor=tk.W)

        btns = ttk.Frame(root)
        btns.pack(fill=tk.X, pady=(0, 8))

        self.btn_elevate = ttk.Button(
            btns, text="Запуск от администратора", command=self._elevate
        )
        self.btn_elevate.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_start = ttk.Button(
            btns, text="Очистить", command=self._start_cleanup
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_repair = ttk.Button(
            btns, text="Починить клавиатуру/мышь", command=self._start_repair
        )
        self.btn_repair.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(btns, text="Очистить лог", command=self._clear_log).pack(
            side=tk.LEFT
        )

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(0, 8))

        log_frame = ttk.LabelFrame(root, text="Журнал", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            height=16,
            bg="#121212",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 9),
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        scroll = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._append_log(
            "Отключите USB-накопители перед очисткой. "
            "Клавиатуры/мыши/HID не удаляются. "
            "Требуются права администратора."
        )

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        if busy:
            self.btn_start.state(["disabled"])
            self.btn_elevate.state(["disabled"])
            self.btn_repair.state(["disabled"])
            self.progress.start(12)
        else:
            self.progress.stop()
            self._refresh_admin_status()
            if is_admin():
                self.btn_repair.state(["!disabled"])
            else:
                self.btn_repair.state(["disabled"])

    def _refresh_admin_status(self) -> None:
        if is_admin():
            self.admin_var.set("Статус: запущено от администратора")
            self.btn_elevate.state(["disabled"])
            if not self._running:
                self.btn_start.state(["!disabled"])
                self.btn_repair.state(["!disabled"])
        else:
            self.admin_var.set(
                "Статус: нет прав администратора — нажмите кнопку ниже"
            )
            self.btn_elevate.state(["!disabled"])
            self.btn_start.state(["disabled"])
            self.btn_repair.state(["disabled"])

    def _append_log(self, msg: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{_ts()}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _drain_log_queue(self) -> None:
        try:
            while True:
                self._append_log(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _elevate(self) -> None:
        if is_admin():
            messagebox.showinfo("fast_clear", "Уже запущено от администратора.")
            return
        if relaunch_as_admin():
            self.destroy()
        else:
            messagebox.showerror(
                "fast_clear",
                "Не удалось запросить повышение прав (UAC отклонён?).",
            )

    def _start_cleanup(self) -> None:
        if self._running:
            return
        if not is_admin():
            messagebox.showwarning(
                "fast_clear",
                "Сначала запустите программу от имени администратора.",
            )
            return

        opts = CleanupOptions(
            do_registry=self.var_registry.get(),
            do_eventlogs=self.var_eventlogs.get(),
            do_files=self.var_files.get(),
            do_self_clean=self.var_self.get(),
        )
        if not any(
            (
                opts.do_registry,
                opts.do_eventlogs,
                opts.do_files,
                opts.do_self_clean,
            )
        ):
            messagebox.showinfo("fast_clear", "Выберите хотя бы один пункт.")
            return

        if not messagebox.askyesno(
            "fast_clear",
            "Будут очищены следы USB в выбранных областях.\n"
            "Журналы System/Security также будут очищены при включённой "
            "самоочистке.\n\nПродолжить?",
            icon="warning",
        ):
            return

        self._running = True
        self._finish_ok = None
        self._set_busy(True)
        self._append_log(f"Старт очистки (fast_clear {__version__})")

        def worker() -> None:
            ok = False
            try:
                summary = run_cleanup(
                    options=opts,
                    progress=lambda m: self._log_queue.put(m),
                )
                self._log_queue.put(format_summary(summary))
                ok = summary.error is None
                if summary.error:
                    self._log_queue.put(f"Сбой: {summary.error}")
            except Exception as exc:  # noqa: BLE001
                self._log_queue.put(f"Исключение: {exc}")
                ok = False
            self._finish_ok = ok

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()
        self.after(200, self._poll_worker)

    def _start_repair(self) -> None:
        if self._running:
            return
        if not is_admin():
            messagebox.showwarning(
                "fast_clear",
                "Сначала запустите программу от имени администратора.",
            )
            return
        self._finish_ok = None
        self._set_busy(True)
        self._append_log("Восстановление USB-клавиатуры/мыши…")

        def worker() -> None:
            ok = True
            try:
                from fast_clear.repair import repair_usb_input

                repair_usb_input(progress=lambda m: self._log_queue.put(m))
            except Exception as exc:  # noqa: BLE001
                self._log_queue.put(f"Исключение: {exc}")
                ok = False
            self._finish_ok = ok

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()
        self.after(200, lambda: self._poll_worker(done_title="Восстановление"))

    def _poll_worker(self, done_title: str = "Очистка") -> None:
        if self._worker and self._worker.is_alive():
            self.after(200, lambda: self._poll_worker(done_title=done_title))
            return

        self._set_busy(False)
        ok = bool(self._finish_ok)
        if ok:
            messagebox.showinfo(
                "fast_clear",
                f"{done_title} завершено.\n"
                "Если USB-ввод не ожил — переподключите кабель или перезагрузите ПК.",
            )
        else:
            messagebox.showwarning(
                "fast_clear",
                f"{done_title} завершилось с ошибками. Смотрите журнал.",
            )

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno(
                "fast_clear",
                "Очистка ещё выполняется. Закрыть окно?",
            ):
                return
        self.destroy()


def run_gui() -> int:
    app = FastClearApp()
    app.mainloop()
    return 0


def main() -> None:
    raise SystemExit(run_gui())


if __name__ == "__main__":
    main()
