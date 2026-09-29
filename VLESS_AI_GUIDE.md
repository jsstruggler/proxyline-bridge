# Инструкция и саммари для ИИ-агента: Настройка и валидация VLESS (Xray-core)

Данный документ представляет собой специализированное руководство и базу знаний для автономных агентов и разработчиков по настройке, генерации, валидации и траблшутингу протокола **VLESS** (в связке с **Reality** и **XTLS-Vision**).

---

## 1. Концепция и фундаментальные принципы

* **VLESS (Virtual Less)** — легковесный протокол проксирования без встроенного уровня шифрования данных (stateless). В отличие от VMess, он не расходует ресурсы CPU на двойное шифрование и не требует синхронизации времени для хэширования пакетов.
* **Делегирование безопасности** — шифрование и маскировка целиком передаются нижележащему транспортному слою: **Reality** или **TLS**.
* **VLESS-Reality + XTLS-Vision** — современный де-факто стандарт обхода продвинутых DPI-систем и активного зондирования (Active Probing):
  * **Без собственного домена и сертификатов**: сервер «крадет» TLS-рукопожатие у реально существующего веб-сайта (сайта-донора).
  * **XTLS-Vision (`xtls-rprx-vision`)**: обеспечивает прямое проксирование TLS-трафика и добавляет псевдослучайный паддинг (padding), устраняя характерные паттерны размера пакетов TLS-in-TLS.
  * **uTLS Fingerprint**: маскирует клиентские отпечатки Client Hello под реальные браузеры (Chrome, Firefox, Safari).

---

## 2. Справочник параметров (Матрица конфигурации)

| Параметр | JSON-ключ (Xray / Client) | URI Query-параметр | Тип / Допустимые значения | Описание и критические правила |
| :--- | :--- | :--- | :--- | :--- |
| **UUID** | `id` | Путь перед `@` | UUID v4 (`xray uuid`) | Обязательный уникальный идентификатор клиента |
| **Шифрование** | `encryption` / `decryption` | `encryption` | Строго `"none"` | **Никогда** не указывать `auto`, `aes-128-gcm` и т.д. |
| **Поток** | `flow` | `flow` | `xtls-rprx-vision` или отсутствует | Разрешен **только** для `network: "tcp"` при `security: "reality"` или `tls` |
| **Транспорт** | `network` | `type` | `tcp`, `ws`, `grpc`, `h2` | Для Reality рекомендуется `tcp`. Для CDN — `ws` |
| **Безопасность**| `security` | `security` | `reality`, `tls`, `none` | Для устойчивого обхода блокировок — `reality` |
| **SNI** | `serverName` | `sni` | FQDN (напр. `apple.com`) | Имя маскировочного сайта |
| **Target Dest** | `dest` | — *(только сервер)* | `FQDN:443` или `IP:443` | Реальный сервер-донор (только на стороне сервера) |
| **Приватный ключ** | `privateKey` | — *(только сервер)* | Base64-строка X25519 | Секретный ключ сервера (из `xray x25519`) |
| **Публичный ключ** | `publicKey` | `pbk` | Base64-строка X25519 | Публичный ключ для клиента (из `xray x25519`) |
| **Short ID** | `shortId` / `shortIds` | `sid` | Hex-строка (обычно 8–16 hex) | Идентификатор сессии Reality для защиты от реплея |
| **Отпечаток** | `fingerprint` | `fp` | `chrome`, `firefox`, `safari`, `ios` | Браузерный отпечаток Client Hello (uTLS) |
| **SpiderX** | `spiderX` | `spx` | Путь (обычно `/`) | Эмуляция глубины сканирования сайта Reality |
| **WS Path** | `path` | `path` | URL-путь (напр. `/chat`) | Используется только при `network: "ws"` |
| **WS Host** | `headers.Host` | `host` | FQDN | Host-заголовок при `network: "ws"` |
| **gRPC Service**| `serviceName` | `serviceName` | Строка | Имя сервиса при `network: "grpc"` |

---

## 3. Анатомия VLESS URI

### 3.1. VLESS + Reality (TCP + Vision) — Рекомендуемый
```text
vless://<UUID>@<SERVER_HOST>:<PORT>?type=tcp&security=reality&flow=xtls-rprx-vision&pbk=<PUBLIC_KEY>&fp=chrome&sni=<SNI>&sid=<SHORT_ID>&spx=%2F#<REMARK>
```
*Пример:*
```text
vless://b831381d-6324-4d53-ad4f-8cda48b30811@198.51.100.1:443?type=tcp&security=reality&flow=xtls-rprx-vision&pbk=WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY&fp=chrome&sni=apple.com&sid=6ba85179e30d4fc2&spx=%2F#Production-Reality
```

### 3.2. VLESS + WebSocket + TLS (Для проксирования через Cloudflare CDN)
```text
vless://<UUID>@<SERVER_HOST>:<PORT>?type=ws&security=tls&path=%2Fcustom-ws&host=<CDN_DOMAIN>&sni=<CDN_DOMAIN>&fp=chrome#Production-WS
```

---

## 4. Эталонные конфигурации

### 4.1. Серверная конфигурация (Xray-core: `inbounds`)

Файл `/usr/local/etc/xray/config.json`:

```json
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "listen": "0.0.0.0",
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "b831381d-6324-4d53-ad4f-8cda48b30811",
            "flow": "xtls-rprx-vision"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "www.apple.com:443",
          "xver": 0,
          "serverNames": [
            "www.apple.com",
            "apple.com"
          ],
          "privateKey": "<SERVER_PRIVATE_KEY_HERE>",
          "shortIds": [
            "6ba85179e30d4fc2"
          ]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"]
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    },
    {
      "protocol": "blackhole",
      "tag": "block"
    }
  ]
}
```

### 4.2. Клиентская конфигурация (Xray-core Outbound)

```json
{
  "tag": "proxy",
  "protocol": "vless",
  "settings": {
    "vnext": [
      {
        "address": "198.51.100.1",
        "port": 443,
        "users": [
          {
            "id": "b831381d-6324-4d53-ad4f-8cda48b30811",
            "flow": "xtls-rprx-vision",
            "encryption": "none",
            "level": 0
          }
        ]
      }
    ]
  },
  "streamSettings": {
    "network": "tcp",
    "security": "reality",
    "realitySettings": {
      "show": false,
      "fingerprint": "chrome",
      "serverName": "www.apple.com",
      "publicKey": "<PUBLIC_KEY_HERE>",
      "shortId": "6ba85179e30d4fc2",
      "spiderX": "/"
    }
  }
}
```

### 4.3. Клиентская конфигурация (Sing-box Outbound)

```json
{
  "type": "vless",
  "tag": "vless-out",
  "server": "198.51.100.1",
  "server_port": 443,
  "uuid": "b831381d-6324-4d53-ad4f-8cda48b30811",
  "flow": "xtls-rprx-vision",
  "network": "tcp",
  "tls": {
    "enabled": true,
    "server_name": "www.apple.com",
    "utls": {
      "enabled": true,
      "fingerprint": "chrome"
    },
    "reality": {
      "enabled": true,
      "public_key": "<PUBLIC_KEY_HERE>",
      "short_id": "6ba85179e30d4fc2"
    }
  }
}
```

---

## 5. Памятка по развертыванию на сервере (CLI)

```bash
# 1. Установка Xray-core на сервере
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)"

# 2. Генерация пары ключей X25519 для Reality
xray x25519
# Вывод содержит Private key (для сервера) и Public key (для клиента)

# 3. Генерация UUID пользователя
xray uuid

# 4. Генерация Short ID (hex)
openssl rand -hex 8

# 5. Проверка пригодности сайта-донора (поддержка TLS 1.3 и HTTP/2)
curl -vI --tlsv1.3 --http2 https://www.apple.com

# 6. Проверка синтаксиса конфигурации Xray
xray run -test -conf /usr/local/etc/xray/config.json

# 7. Открытие порта в фаерволе и запуск службы
ufw allow 443/tcp
systemctl restart xray
systemctl enable xray

# 8. Включение синхронизации времени (NTP)
timedatectl set-ntp on
```

---

## 6. Правила валидации для ИИ-агентов (Инварианты)

1. **Правило потока (Flow Rule):**
   * Значение `flow: "xtls-rprx-vision"` допускается **исключительно** при `network: "tcp"` и `security: "reality"` или `security: "tls"`.
   * При использовании `ws`, `grpc` или `h2` параметр `flow` обязан отсутствовать (быть пустой строкой или `null`).
2. **Правило шифрования (Encryption Rule):**
   * В секции VLESS поле `encryption` всегда принимает значение `"none"`. Никаких `aes`, `chacha` или иных шифров.
3. **Требования к сайту Reality (SNI / Dest):**
   * Домен маскировки обязан поддерживать протокол **TLS 1.3** и расширение **ALPN `h2`**.
   * Нельзя использовать домены, защищенные Cloudflare (если сам сервер не настроен через Cloudflare CDN), так как это приводит к ошибкам сопоставления сертификата.
4. **Порт по умолчанию:**
   * Для Reality настоятельно рекомендуется порт `443`. Использование нестандартных портов (например, 8443, 2053) демаскирует сервер перед DPI.
5. **Синхронизация времени (Time Drift):**
   * Рассинхронизация часов между клиентом и сервером не должна превышать ±60 секунд во избежание сбоев проверки временных меток TLS-рукопожатия.

---

## 7. Траблшутинг (Поиск и устранение неисправностей)

| Ошибка / Симптом | Причина | Шаги решения |
| :--- | :--- | :--- |
| `i/o timeout` при подключении | Закрыт порт 443 на сервере или в панели провайдера | Выполнить `ufw allow 443/tcp`; проверить Security Groups / Firewall в облаке (AWS, Hetzner, DO). |
| `tls: handshake failure` / `bad certificate` | Несовпадение `publicKey`, неверный `sni` или сайт-донор блокирует запросы | Проверить соответствие `publicKey` и `privateKey` (`xray x25519`); сменить SNI. |
| Соединение рвется после скачивания первых нескольких килобайт/мегабайт | Неправильная связка `flow` или отсутствие `fp` (uTLS) | Убедиться, что `flow: "xtls-rprx-vision"` и `fp: "chrome"`. При нестабильном канале попробовать сменить отпечаток. |
| `xtls-rprx-vision only support TLS 1.3` | Маскировочный сервер ответил по TLS 1.2 | Заменить сайт в `dest` / `sni` на гарантированно поддерживающий TLS 1.3 (Apple, Google, Microsoft). |
| Клиент не видит интернет, но пинг идет | Ошибка маршрутизации outbounds на сервере | Проверить наличие исходящего правила `freedom` ("tag": "direct") в конфиге сервера Xray. |
