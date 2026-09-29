# Документация проекта Proxyline Bridge

## 1. Обзор проекта

**Proxyline Bridge** — это кроссплатформенное приложение-мост, которое принимает конфигурации удаленных прокси различных протоколов и запускает локальный HTTP-прокси без авторизации на `127.0.0.1:<случайный_порт>`. 

Это позволяет браузерным расширениям (Chrome, Firefox и др.), десктопным программам и скриптам работать через сложные или защищенные протоколы прокси без необходимости встроенной поддержки шифрования или специализированных клиентов в самих расширениях.

### Поддерживаемые протоколы:
- **SOCKS5** (с логином/паролем или без)
- **HTTP / HTTPS** (с авторизацией или без)
- **Shadowsocks** (SIP002, legacy base64, прямое указание метода и пароля)
- **VLESS** (VLESS + Reality, WebSocket, gRPC, TLS, flow `xtls-rprx-vision`)

---

## 2. Архитектура и компоненты

Проект состоит из модульной архитектуры на Python:

```
proxyline-bridge/
├── bridge/
│   ├── __init__.py           # Экспорт основных сущностей пакета bridge
│   ├── config_parser.py      # Парсер URL и строк конфигураций всех протоколов
│   ├── xray_manager.py       # Менеджер бинарного файла Xray-core и запуск подпроцесса
│   └── proxy_service.py      # Единый сервис управления активными прокси и переключением
├── linux/                    # Десктоп-интеграция для Linux (.desktop, иконка)
├── tests/
│   ├── test_api.py           # Интеграционные тесты API FastAPI
│   └── test_config_parser.py # Модульные тесты парсера конфигураций
├── .github/workflows/
│   └── build.yml             # CI/CD сборки под macOS, Windows, Linux
├── main.py                   # Точка входа: FastAPI + системный трей (macOS/Windows/Linux)
├── updater.py                # Модуль автоматического обновления
├── proxyline-bridge.spec     # Конфигурация сборки PyInstaller
├── requirements.txt          # Зависимости Python
├── pytest.ini                # Конфигурация тестов pytest
└── DOCUMENTATION.md          # Данная документация
```

### Движки прокси:
1. **`proxy-relay`** (Python asyncio):
   - Используется для протоколов **SOCKS5** и **HTTP**.
   - Обеспечивает легковесное туннелирование без внешних зависимостей.
2. **`Xray-core`** (высокопроизводительный Go-движок):
   - Используется для протоколов **Shadowsocks** и **VLESS**.
   - Позволяет поддерживать современные алгоритмы обхода блокировок: XTLS, Reality, Vision, AEAD-шифры Shadowsocks (включая Shadowsocks 2022).

---

## 3. Модули ядра (`bridge/`)

### 3.1. `bridge/config_parser.py`
Отвечает за валидацию, парсинг и нормализацию любых форматов входящих строк.

- **Класс `ProxyProtocol`**: Enum со значениями `socks5`, `http`, `shadowsocks`, `vless`.
- **Класс `ParsedProxyConfig`**: Pydantic-модель, хранящая нормализованные параметры подключения.
  - Метод `to_upstream_url()`: формирует URL для `proxy-relay` (для socks5/http).
  - Метод `to_xray_outbound()`: формирует секцию `outbound` конфигурации Xray JSON для VLESS или Shadowsocks.
- **Функция `parse_proxy_config(config: str, protocol: Optional[str] = None)`**:
  - Распознает схемы `vless://`, `ss://`, `socks5://`, `http://`.
  - Автоматически распознает 4-частный формат `ip:port:p3:p4`:
    - Если `p3` или `p4` совпадает с известным методом Shadowsocks (например, `aes-256-gcm`), или передан `protocol="shadowsocks"` — обрабатывается как Shadowsocks.
    - В противном случае — классический формат SOCKS5 `ip:port:login:password`.
  - Поддерживает парсинг параметров VLESS: `security=reality`, `sni`, `pbk`, `sid`, `spx`, `fp`, `flow`, `type` (`tcp`, `ws`, `grpc`), `path`, `serviceName`.
  - Поддерживает безопасное декодирование base64 с автоматическим выравниванием padding (`safe_b64decode`).

### 3.2. `bridge/xray_manager.py`
Управляет поиском, автоматической загрузкой и жизненным циклом бинарного файла Xray-core.

- **`XrayManager`**:
  - Ищет существующий бинарник Xray в следующем порядке:
    1. Переменная окружения `PROXYLINE_XRAY_PATH` или `XRAY_PATH`.
    2. Встроенный каталог PyInstaller (`sys._MEIPASS/bin` или `sys._MEIPASS`).
    3. Каталог рядом с исполняемым файлом приложения (`sys.executable`).
    4. Локальная папка проекта `bin/xray`.
    5. Пользовательский кэш: `~/.proxyline-bridge/bin/xray` (или `.exe` на Windows).
    6. Системный `PATH`.
  - Если файл не найден: функция `download_binary()` автоматически скачивает официальный релиз Xray с GitHub Releases для текущей ОС и архитектуры (`arm64`, `x86_64`), распаковывает в `~/.proxyline-bridge/bin/` и выставляет права на исполнение (`0o755`).
- **`XrayRunner`**:
  - Находит свободный TCP-порт локально (`find_free_port()`).
  - Генерирует временный конфигурационный JSON с входящим unauthenticated HTTP прокси на `127.0.0.1:<port>` и исходящим прокси (VLESS или Shadowsocks).
  - Запускает процесс `xray run -c <config_path>` без создания консольного окна на Windows (`CREATE_NO_WINDOW`).
  - Проверяет успешность старта (анализирует код возврата и stdout/stderr).
  - Дожидается готовности порта (`_wait_for_port`).
  - Метод `stop()`: корректно завершает процесс (`SIGTERM` -> `SIGKILL` по таймауту) и удаляет временный файл конфигурации.
  - Автоматически зарегистрирован в `atexit` для очистки при выходе из приложения.

### 3.3. `bridge/proxy_service.py`
- **`ProxyBridgeService`**:
  - Центральный координатор приложения.
  - Потокобезопасен (использует `asyncio.Lock`).
  - При установке нового прокси через `set_proxy`:
    - Останавливает предыдущий прокси (независимо от того, был ли это `proxy-relay` или `XrayRunner`).
    - Запускает нужный бэкенд в зависимости от протокола.
    - Вызывает колбэк `on_status_change` для синхронного обновления заголовка и меню системного трея.
    - Возвращает URL локального HTTP-прокси `http://127.0.0.1:<port>`.
  - Метод `stop_proxy()`: безопасно гасит любой активный прокси и переводит трей в режим ожидания.
  - Метод `get_proxy()`: возвращает текущее состояние и активный порт.

---

## 4. Спецификация REST API

Сервер FastAPI запускается по умолчанию на `http://127.0.0.1:8000`.

### 4.1. Установка прокси: `POST /set_proxy`

**Тело запроса (`application/json`):**
```json
{
  "config": "<строка конфигурации>",
  "protocol": "<необязательный протокол: socks5 | shadowsocks | vless | http>"
}
```

#### Примеры конфигураций:

1. **SOCKS5 (4 части):**
```json
{
  "config": "192.168.1.1:1080:myuser:mypassword"
}
```

2. **Shadowsocks (URL SIP002):**
```json
{
  "config": "ss://YWVzLTI1Ni1nY206c2VjcmV0MTIz@198.51.100.1:8388#MyServer"
}
```

3. **Shadowsocks (4 части):**
```json
{
  "config": "198.51.100.1:8388:aes-256-gcm:secret123"
}
```

4. **VLESS + Reality:**
```json
{
  "config": "vless://b831381d-6324-4d53-ad4f-8cda48b30811@198.51.100.1:443?security=reality&sni=yahoo.com&fp=chrome&pbk=WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY&sid=123456&type=tcp&flow=xtls-rprx-vision#MyReality"
}
```

5. **VLESS + WebSocket + TLS:**
```json
{
  "config": "vless://b831381d-6324-4d53-ad4f-8cda48b30811@example.com:443?security=tls&sni=example.com&type=ws&path=%2Fchat#MyWs"
}
```

**Ответ (200 OK):**
```json
{
  "local_proxy": "http://127.0.0.1:51234",
  "protocol": "vless",
  "tag": "MyReality"
}
```

**Ошибки:**
- `400 Bad Request` — неверный формат строки конфигурации или отсутствуют обязательные поля.
- `500 Internal Server Error` — ошибка запуска фонового процесса Xray или сервиса.

---

### 4.2. Получение текущего прокси: `GET /get_proxy`

**Ответ, если прокси активен (200 OK):**
```json
{
  "local_proxy": "http://127.0.0.1:51234",
  "protocol": "vless",
  "tag": "MyReality"
}
```

**Ответ, если прокси отключен (200 OK):**
```json
{
  "local_proxy": null,
  "protocol": null
}
```

---

### 4.3. Остановка прокси: `POST /stop_proxy` или `DELETE /proxy`

**Ответ (200 OK):**
```json
{
  "status": "stopped"
}
```

---

### 4.4. Список поддерживаемых протоколов: `GET /protocols`

**Ответ (200 OK):**
```json
{
  "protocols": ["socks5", "http", "shadowsocks", "vless"],
  "version": "1.0.14"
}
```

---

## 5. Системный трей и интерфейс

Приложение автоматически интегрируется в панель задач/строку меню:
- **macOS**: используется библиотека `rumps`. В панели меню отображается:
  - В режиме ожидания: `🌐 Bridge v1.0.14` (в меню: `Status: Waiting for proxy...`).
  - При активном прокси: `🌐 Active (VLESS)` (в меню: `Status: Proxy active (port 51234, VLESS)`).
- **Windows / Linux**: используется `PySide6` (`QSystemTrayIcon`). Всплывающая подсказка и меню обновляются динамически при установке или смене прокси.

---

## 6. Сборка и распространение

### 6.1. Локальная сборка PyInstaller
Сборка осуществляется через `proxyline-bridge.spec`:
```bash
pyinstaller proxyline-bridge.spec --clean -y
```
- Скрипт сборки автоматически проверяет наличие `bin/xray` (или `bin/xray.exe`) и вшивает его в результирующий дистрибутив.
- Все модули `bridge.*` включены в `hiddenimports`.

### 6.2. CI/CD в GitHub Actions (`.github/workflows/build.yml`)
При создании тега `v*` запускается матрица сборки:
- **macOS**: `macos-latest` (Apple Silicon arm64) и `macos-13` (Intel x86_64) -> сборка DMG через `dmgbuild`.
- **Windows**: `windows-latest` (x86_64) и `windows-11-arm` (arm64) -> сборка `.exe`.
- **Linux**: `ubuntu-latest` (amd64) и `ubuntu-24.04-arm` (arm64) -> сборка бинарника и упаковка `.deb` пакета.
- Перед сборкой пайплайн выполняет шаг `Download Xray Core`, предварительно упаковывая актуальный бинарник Xray под целевую ОС и архитектуру.

---

## 7. Тестирование

Проект покрыт автоматическими тестами `pytest`:
- `tests/test_config_parser.py`: тестирование парсинга всех типов ссылок и строк, генерации JSON outbounds, обработки ошибок.
- `tests/test_api.py`: тестирование всех эндпоинтов FastAPI, переключения протоколов, остановки прокси и валидации.

### Запуск тестов:
```bash
pytest -v
```

---

## 8. Дополнительные руководства

- [VLESS_AI_GUIDE.md](file:///Users/aleksandr/proxyline-bridge/VLESS_AI_GUIDE.md) — специализированное руководство и база знаний для ИИ-агентов по настройке, генерации и валидации конфигураций VLESS (Reality, Vision, gRPC, WebSocket).
