# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии следуют [Semantic Versioning](https://semver.org/lang/ru/).

## [1.2.0] — 2026-07-16

### Добавлено

- Очистка следов USB-модемов (`Enum\Modem`, Class Modem/Ports, usbser, WWAN).
- Очистка телефонов и часов (MTP/WPD, UMB, DeviceContainers, Autoplay KnownDevices).
- Кэши ПО: Apple Mobile Device Support, Garmin, Samsung, ADB (ветки устройств).
- Журналы: WPD-MTPUS, WWAN, Mobile Broadband, ModemDeviceEvents.
- Prefetch/BAM: Garmin, AppleMobile, adb.

## [1.1.0] — 2026-07-16

### Добавлено

- Графический интерфейс (tkinter): выбор модулей, лог, UAC-кнопка.
- Сборка standalone `fast_clear.exe` через PyInstaller (`build_exe.bat` / `build_exe.ps1`).
- Общий модуль `cleanup.py` для CLI и GUI.
- Флаги `--gui` / `--cli`; exe по умолчанию открывает GUI и запрашивает админа (UAC).

## [1.0.0] — 2026-07-16

### Добавлено

- Первая публичная версия `fast_clear` для Windows 10/11.
- Очистка реестра: `USBSTOR` / `USB` / `WPD` / `WPDBUSENUM`, Portable Devices, DeviceClasses, MountedDevices (USB), EMDMgmt, BAM.
- Снятие ACL и удаление защищённых ключей `Enum\...\Properties` (SeTakeOwnership / Backup / Restore).
- Очистка журналов событий через `wevtutil` (PnP/USB/Storage + System/Security/Eventlog).
- Обнуление SetupAPI-логов, удаление Prefetch утилит очистки, истории PowerShell.
- Финальная самоочистка следов очистки (повторный clear audit-журналов, Prefetch `wevtutil`).
- CLI: `--dry-run`, выборочный skip модулей, `--version`, `-q`.
- `VERSION`, `__version__`, README, `run_as_admin.bat`.

[1.2.0]: https://github.com/local/fast_clear/releases/tag/v1.2.0
[1.1.0]: https://github.com/local/fast_clear/releases/tag/v1.1.0
[1.0.0]: https://github.com/local/fast_clear/releases/tag/v1.0.0
