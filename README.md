# Proxyline Bridge

A bridge application that accepts a SOCKS5 proxy configuration (with authentication) and starts a local unauthenticated HTTP proxy that can be used directly in browser extensions.

This uses the [proxy-relay](https://pypi.org/project/proxy-relay/) library to handle the protocol conversion and relaying.

## Requirements

- Python 3.7+

## Installation

```bash
pip install -r requirements.txt
```

## Running the bridge

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

## Usage

### 1. Set a proxy
The browser extension can send a POST request with the proxy configuration.

```bash
curl -X POST http://127.0.0.1:8000/set_proxy \
     -H "Content-Type: application/json" \
     -d '{"config": "192.168.1.1:1080:myuser:mypassword"}'
```

**Response:**
```json
{
  "local_proxy": "http://127.0.0.1:51234"
}
```

The extension should then configure Chrome to use `http://127.0.0.1:51234` as the proxy.

### 2. Get the current active proxy
```bash
curl http://127.0.0.1:8000/get_proxy
```

**Response:**
```json
{
  "local_proxy": "http://127.0.0.1:51234"
}
```
