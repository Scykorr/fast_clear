# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии следуют [Semantic Versioning](https://semver.org/lang/ru/).

## [1.3.2] — 2026-07-19

### Исправлено (безопасность данных)

- **Внутренние диски больше не могут пострадать.** Убран слишком широкий шаблон
  `DISK&VEN` в `TARGET_RE`, который теоретически совпадал с внутренним
  `SCSI\Disk&Ven_NVMe…`. USB-флешки и внешние USB-HDD по-прежнему ловятся по
  признаку шины `USBSTOR`.
- **`MountedDevices`: буквы C:/D: защищены.** Удаление теперь только по маркеру
  съёмной шины `USBSTOR`/`WPDBUSENUM`; убраны совпадения по имени вендора
  (в т.ч. `KINGSTON` — это вендор системного диска).

### Добавлено

- Кнопка «Починить USB и сеть»: помимо USB перезапускает `Dhcp/Dnscache/WlanSvc/
  NlaSvc`, делает `ipconfig /flushdns` и `/renew` и проверяет доступ в Интернет.
  Сохранённые Wi-Fi профили (пароли) не удаляются.

### Проверено

- После очистки: Интернет доступен (ping), 11 сохранённых Wi-Fi сетей на месте,
  буквы C:/D: не тронуты, новые флешки/HDD монтируются (pnputil-подход).

## [1.3.1] — 2026-07-19

### Исправлено (критично — HistoryChecker)

- **Вкладки «Сети WiFi» и «Факты подключения к Интернет».** HistoryChecker
  читает `Microsoft-Windows-WLAN-AutoConfig/Operational` (SSID/MAC/время) и
  `Microsoft-Windows-UniversalTelemetryClient/Operational` (события 27/61 —
  «Интернет есть/отсутствует»). Эти каналы раньше не чистились. Добавлены.
- **Вкладка «USB-устройства» всё ещё показывала флешки.** Причина — неверный
  GUID WPD в `DeviceClasses` (`{6ac27878-a6fa-…}` не чистился) плюс баг
  `MountedDevices`: значения UTF-16LE не ловились ASCII-поиском `USBSTOR`
  (буква `F:` оставалась с Transcend). Оба бага исправлены.
- Добавлены каналы, которые явно читает HistoryChecker: `Kernel-PnPConfig`,
  `Partition/Diagnostic`, `Storsvc/Diagnostic`, `DriverFrameworks-UserMode`,
  `DeviceSetupManager/Admin`, `NCSI`, `NetworkProfile`.

### Добавлено

- Модуль `network_clean.py` — очистка `NetworkList\Profiles/Signatures/Nla`
  (имена сетей и даты подключений в реестре).
- Опции `--skip-network` / `--wlan-profiles` и чекбоксы в GUI.
- VID Seagate / JMicron / ASMedia / SanDisk / Kingston / Transcend в цели.

## [1.3.0] — 2026-07-18

### Исправлено (критично)

- **Не подключаются новые флешки после очистки.** Причина — грубое удаление веток
  `Enum\USB` / `Enum\USBSTOR` со сменой владельца ломало PnP-регистрацию.
  Теперь устройства удаляются штатно через `pnputil /remove-device`, что не
  повреждает подсистему USB.
- **Программа-детектор всё ещё видела старые флешки.** Не вычищались остаточные
  phantom-ноды `STORAGE\Volume\_??_USBSTOR#…`, `SWD\WPDBUSENUM`, а также
  `Amcache.hve` и ротированные логи `setupapi`. Теперь чистятся.
- **Детектор сообщал, что журнал System был изменён (Event ID 104).** `wevtutil cl`
  всегда оставляет запись «журнал очищен». Теперь журналы стираются через
  остановку службы `EventLog` и удаление `.evtx` — событие 104/1102 не создаётся.

### Добавлено

- Модуль `device_clean.py` — безопасное удаление истории накопителей/телефонов/
  часов/модемов через `pnputil` (клавиатуры, мыши, HID, хабы не трогаются).
- `eventlog_clean.wipe_logs_via_service()` — стирание журналов без следа очистки.
- Очистка `Amcache.hve` (ветки `InventoryDevicePnp`) и всех логов `setupapi.*`.
- Восстановление USB расширено на накопители: удаление phantom-нодов,
  `mountvol /R`, `automount enable`, сброс владельца веток `Enum` на SYSTEM.
  Кнопка GUI переименована в «Починить USB (мышь/клав./флешки)».

## [1.2.1] — 2026-07-16

### Исправлено

- Критично: больше **не очищается весь** `Enum\USB` — сохраняются клавиатуры, мыши, HID и USB-хабы.
- DeviceClasses / DeviceContainers больше не матчятся по голому «USB».
- Добавлены `--repair-input` и кнопка GUI «Починить клавиатуру/мышь».

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

[1.2.1]: https://github.com/local/fast_clear/releases/tag/v1.2.1
[1.2.0]: https://github.com/local/fast_clear/releases/tag/v1.2.0
[1.1.0]: https://github.com/local/fast_clear/releases/tag/v1.1.0
[1.0.0]: https://github.com/local/fast_clear/releases/tag/v1.0.0
