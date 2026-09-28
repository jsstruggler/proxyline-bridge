# Proxyline Bridge

A bridge application that accepts upstream proxy configurations (**SOCKS5**, **HTTP**, **Shadowsocks**, and **VLESS**) and runs a local unauthenticated HTTP proxy that can be used directly in browser extensions, scripts, and applications.

The bridge uses [proxy-relay](https://pypi.org/project/proxy-relay/) for SOCKS5 and HTTP protocols, and embedded/managed [Xray-core](https://github.com/XTLS/Xray-core) for Shadowsocks and VLESS protocols.

## Requirements

- Python 3.9+ (tested up to Python 3.14)
- macOS, Linux, or Windows

## Installation

```bash
pip install -r requirements.txt
```

## Running the bridge

### Development Server:
```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Desktop Application with System Tray:
```bash
python main.py
```

## Usage & API

### 1. Set a proxy (`POST /set_proxy`)

The browser extension or client sends a JSON payload to `/set_proxy`. The bridge automatically recognizes the protocol.

#### SOCKS5 Example (Legacy 4-part or URL):
```bash
curl -X POST http://127.0.0.1:8000/set_proxy \
     -H "Content-Type: application/json" \
     -d '{"config": "192.168.1.1:1080:myuser:mypassword"}'
```

#### Shadowsocks Example:
Supports SIP002 URLs (`ss://base64(method:password)@host:port#tag`), legacy base64 URLs, or `ip:port:method:password`:
```bash
curl -X POST http://127.0.0.1:8000/set_proxy \
     -H "Content-Type: application/json" \
     -d '{"config": "ss://YWVzLTI1Ni1nY206c2VjcmV0MTIz@1.2.3.4:8388#MyServer"}'
```

Or 4-part notation:
```bash
curl -X POST http://127.0.0.1:8000/set_proxy \
     -H "Content-Type: application/json" \
     -d '{"config": "1.2.3.4:8388:aes-256-gcm:secret123"}'
```

#### VLESS Example (Reality, WebSocket, gRPC, TLS):
Supports standard VLESS URLs:
```bash
curl -X POST http://127.0.0.1:8000/set_proxy \
     -H "Content-Type: application/json" \
     -d '{"config": "vless://b831381d-6324-4d53-ad4f-8cda48b30811@1.2.3.4:443?security=reality&sni=yahoo.com&fp=chrome&pbk=WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY&sid=123456&type=tcp&flow=xtls-rprx-vision#MyReality"}'
```

**Response:**
```json
{
  "local_proxy": "http://127.0.0.1:51234",
  "protocol": "vless",
  "tag": "MyReality"
}
```

The browser extension configures Chrome/Firefox to use `http://127.0.0.1:51234` as the local HTTP proxy.

---

### 2. Get the current active proxy (`GET /get_proxy`)

```bash
curl http://127.0.0.1:8000/get_proxy
```

**Response:**
```json
{
  "local_proxy": "http://127.0.0.1:51234",
  "protocol": "vless",
  "tag": "MyReality"
}
```

If no proxy is currently active:
```json
{
  "local_proxy": null,
  "protocol": null
}
```

---

### 3. Stop active proxy (`POST /stop_proxy` or `DELETE /proxy`)

```bash
curl -X POST http://127.0.0.1:8000/stop_proxy
```

**Response:**
```json
{
  "status": "stopped"
}
```

---

### 4. Check supported protocols (`GET /protocols`)

```bash
curl http://127.0.0.1:8000/protocols
```

**Response:**
```json
{
  "protocols": ["socks5", "http", "shadowsocks", "vless"],
  "version": "1.0.14"
}
```

## Running Tests

```bash
pytest -v
```
