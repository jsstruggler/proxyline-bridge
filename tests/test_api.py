"""API integration tests for FastAPI app in main.py."""

import pytest
from fastapi.testclient import TestClient
from main import app, bridge_service


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_protocols_endpoint(client):
    response = client.get("/protocols")
    assert response.status_code == 200
    data = response.json()
    assert "protocols" in data
    assert "vless" in data["protocols"]
    assert "shadowsocks" in data["protocols"]
    assert "socks5" in data["protocols"]
    assert "http" in data["protocols"]


def test_get_proxy_initial(client):
    response = client.get("/get_proxy")
    assert response.status_code == 200
    data = response.json()
    # If no proxy active
    assert "local_proxy" in data


def test_set_and_stop_proxy_socks5(client):
    # Set proxy with SOCKS5 format
    payload = {"config": "127.0.0.1:1080:testuser:testpass"}
    response = client.post("/set_proxy", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "local_proxy" in data
    assert data["local_proxy"].startswith("http://127.0.0.1:")
    assert data.get("protocol") == "socks5"

    # Verify get_proxy
    get_resp = client.get("/get_proxy")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["local_proxy"] == data["local_proxy"]
    assert get_data.get("protocol") == "socks5"

    # Stop proxy
    stop_resp = client.post("/stop_proxy")
    assert stop_resp.status_code == 200
    assert stop_resp.json() == {"status": "stopped"}

    # Verify get_proxy is None
    get_after = client.get("/get_proxy")
    assert get_after.status_code == 200
    assert get_after.json()["local_proxy"] is None


def test_set_proxy_shadowsocks(client):
    # Set proxy with Shadowsocks
    payload = {"config": "1.2.3.4:8388:aes-256-gcm:mypassword"}
    response = client.post("/set_proxy", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "local_proxy" in data
    assert data["local_proxy"].startswith("http://127.0.0.1:")
    assert data.get("protocol") == "shadowsocks"

    # Clean up
    client.post("/stop_proxy")


def test_set_proxy_vless(client):
    # Set proxy with VLESS Reality
    vless_url = (
        "vless://b831381d-6324-4d53-ad4f-8cda48b30811@198.51.100.1:443"
        "?security=reality"
        "&sni=yahoo.com"
        "&fp=chrome"
        "&pbk=WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY"
        "&sid=123456"
        "&type=tcp"
        "#VlessApiTest"
    )
    payload = {"config": vless_url}
    response = client.post("/set_proxy", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "local_proxy" in data
    assert data["local_proxy"].startswith("http://127.0.0.1:")
    assert data.get("protocol") == "vless"
    assert data.get("tag") == "VlessApiTest"

    # Clean up
    client.post("/stop_proxy")


def test_set_proxy_invalid_format(client):
    payload = {"config": "invalid-garbage-format"}
    response = client.post("/set_proxy", json=payload)
    assert response.status_code == 400
    assert "detail" in response.json()


def test_cors_headers(client):
    # Test preflight OPTIONS request
    headers = {
        "Origin": "chrome-extension://testextensionid",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/set_proxy", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "chrome-extension://testextensionid"
    assert response.headers.get("access-control-allow-credentials") == "true"

