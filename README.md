# fast_clear

Утилита для Windows 10 / 11: удаляет следы когда-либо подключённых USB-устройств из реестра, журналов событий и служебных файлов, а также старается убрать следы самой очистки (записи «журнал очищен», Prefetch `wevtutil`, BAM и т.п.).

**Текущая версия:** 1.2.1

## Возможности

| Область | Что очищается |
|--------|----------------|
| Реестр | Флешки (`USBSTOR`), все `Enum\USB`, модемы (`Modem`, COM/Ports), телефоны и часы (WPD/MTP/UMB, WPDBUSENUM), Mobile Broadband, Portable Devices, DeviceContainers, кэши Apple/Garmin/Samsung/ADB |
| Журналы | PnP/USB/Storage, WPD/MTP, WWAN / Mobile Broadband, ModemDeviceEvents, System/Security/Eventlog |
| Файлы | SetupAPI, Prefetch связанных утилит, история PowerShell |
| Самоочистка | Повторный clear журналов с Event ID 104/1102, Prefetch `wevtutil` |
| GUI | Окно с выбором модулей, логом и запросом прав администратора |

## Требования

- Windows 10 или Windows 11
- Для исходников: Python 3.10+ (в проекте есть `venv`)
- Для exe: Python **не нужен** на целевом ПК
- Запуск **от имени администратора**

## Запуск из исходников

```powershell
cd d:\PycharmProjects\fast_clear
.\venv\Scripts\Activate.ps1

python -m fast_clear              # GUI
python -m fast_clear --cli        # консоль
python -m fast_clear --dry-run    # план без изменений
python -m fast_clear --version
```

Или `run_as_admin.bat`.

## Сборка exe (без Python на целевом ПК)

```bat
build_exe.bat
```

или:

```powershell
.\build_exe.ps1
```

Результат: `dist\fast_clear.exe` (один файл, GUI, при старте запрос UAC).

Скрипт ставит PyInstaller в `venv`, собирает onefile через `fast_clear.spec`.

## Параметры CLI

```
python -m fast_clear [опции]

  -V, --version         Версия
  --gui                 Графический интерфейс
  --cli                 Только консоль
  --repair-input        Восстановить USB-клавиатуру/мышь (без очистки)
  --dry-run             План без изменений
  --skip-registry       Не трогать реестр
  --skip-eventlogs      Не очищать журналы
  --skip-files          Не трогать SetupAPI / Prefetch / историю
  --skip-self-clean     Без самоочистки следов
  -q, --quiet           Краткий вывод
```

## Версионирование

- `VERSION` и `fast_clear.__version__`
- [CHANGELOG.md](CHANGELOG.md) — Semantic Versioning

## Ограничения

- Перед запуском **отключите** съёмные USB-накопители.
- Amcache, SRUM, VSS этой версией не очищаются.
- Очистка `Security` / `System` убирает и Event ID 104/1102 («журнал очищен»).
- Для администрирования **своей** системы; полной антифорензики всех артефактов диска нет.

## Структура

```
fast_clear/
  gui.py               # графический интерфейс
  cleanup.py           # общий сценарий очистки
  main.py              # CLI / выбор режима
  ...
build_exe.bat          # сборка exe
build_exe.ps1
fast_clear.spec        # PyInstaller
dist/fast_clear.exe    # после сборки
```

## Лицензия

См. [LICENSE](LICENSE).
