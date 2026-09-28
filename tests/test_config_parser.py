"""Unit tests for proxy configuration parser."""

import base64
import pytest
from bridge.config_parser import (
    ProxyProtocol,
    parse_proxy_config,
    safe_b64decode,
)


def test_socks5_legacy_4part():
    cfg = parse_proxy_config("192.168.1.100:1080:testuser:testpass")
    assert cfg.protocol == ProxyProtocol.SOCKS5
    assert cfg.host == "192.168.1.100"
    assert cfg.port == 1080
    assert cfg.username == "testuser"
    assert cfg.password == "testpass"
    assert cfg.to_upstream_url() == "socks5://testuser:testpass@192.168.1.100:1080"


def test_socks5_url():
    cfg = parse_proxy_config("socks5://alice:secret@example.com:1080#Primary")
    assert cfg.protocol == ProxyProtocol.SOCKS5
    assert cfg.host == "example.com"
    assert cfg.port == 1080
    assert cfg.username == "alice"
    assert cfg.password == "secret"
    assert cfg.tag == "Primary"


def test_http_url():
    cfg = parse_proxy_config("http://bob:mypass@10.0.0.5:8080#Work")
    assert cfg.protocol == ProxyProtocol.HTTP
    assert cfg.host == "10.0.0.5"
    assert cfg.port == 8080
    assert cfg.username == "bob"
    assert cfg.password == "mypass"
    assert cfg.tag == "Work"


def test_shadowsocks_sip002():
    auth = base64.b64encode(b"aes-256-gcm:p@ssw0rd!").decode()
    url = f"ss://{auth}@1.2.3.4:8388#MySS"
    cfg = parse_proxy_config(url)
    assert cfg.protocol == ProxyProtocol.SHADOWSOCKS
    assert cfg.host == "1.2.3.4"
    assert cfg.port == 8388
    assert cfg.method == "aes-256-gcm"
    assert cfg.password == "p@ssw0rd!"
    assert cfg.tag == "MySS"

    outbound = cfg.to_xray_outbound()
    assert outbound["protocol"] == "shadowsocks"
    assert outbound["settings"]["servers"][0]["address"] == "1.2.3.4"
    assert outbound["settings"]["servers"][0]["port"] == 8388
    assert outbound["settings"]["servers"][0]["method"] == "aes-256-gcm"
    assert outbound["settings"]["servers"][0]["password"] == "p@ssw0rd!"


def test_shadowsocks_legacy_base64():
    raw = b"chacha20-ietf-poly1305:secret@ss.example.org:9000"
    b64 = base64.b64encode(raw).decode()
    url = f"ss://{b64}#LegacySS"
    cfg = parse_proxy_config(url)
    assert cfg.protocol == ProxyProtocol.SHADOWSOCKS
    assert cfg.host == "ss.example.org"
    assert cfg.port == 9000
    assert cfg.method == "chacha20-ietf-poly1305"
    assert cfg.password == "secret"
    assert cfg.tag == "LegacySS"


def test_shadowsocks_4part_autodetect():
    # host:port:method:password
    cfg1 = parse_proxy_config("95.216.0.1:8388:aes-128-gcm:mysecret")
    assert cfg1.protocol == ProxyProtocol.SHADOWSOCKS
    assert cfg1.method == "aes-128-gcm"
    assert cfg1.password == "mysecret"

    # host:port:password:method
    cfg2 = parse_proxy_config("95.216.0.1:8388:mysecret:2022-blake3-aes-128-gcm")
    assert cfg2.protocol == ProxyProtocol.SHADOWSOCKS
    assert cfg2.method == "2022-blake3-aes-128-gcm"
    assert cfg2.password == "mysecret"


def test_shadowsocks_with_protocol_hint():
    cfg = parse_proxy_config("1.2.3.4:8388:custommethod:mypassword", protocol="shadowsocks")
    assert cfg.protocol == ProxyProtocol.SHADOWSOCKS
    assert cfg.host == "1.2.3.4"
    assert cfg.port == 8388


def test_vless_reality():
    url = (
        "vless://b831381d-6324-4d53-ad4f-8cda48b30811@198.51.100.1:443"
        "?security=reality"
        "&sni=yahoo.com"
        "&fp=chrome"
        "&pbk=WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY"
        "&sid=123456"
        "&type=tcp"
        "&flow=xtls-rprx-vision"
        "#RealityNode"
    )
    cfg = parse_proxy_config(url)
    assert cfg.protocol == ProxyProtocol.VLESS
    assert cfg.host == "198.51.100.1"
    assert cfg.port == 443
    assert cfg.uuid == "b831381d-6324-4d53-ad4f-8cda48b30811"
    assert cfg.security == "reality"
    assert cfg.sni == "yahoo.com"
    assert cfg.fingerprint == "chrome"
    assert cfg.public_key == "WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY"
    assert cfg.short_id == "123456"
    assert cfg.flow == "xtls-rprx-vision"
    assert cfg.tag == "RealityNode"

    outbound = cfg.to_xray_outbound()
    assert outbound["protocol"] == "vless"
    assert outbound["settings"]["vnext"][0]["address"] == "198.51.100.1"
    assert outbound["settings"]["vnext"][0]["port"] == 443
    assert outbound["settings"]["vnext"][0]["users"][0]["id"] == "b831381d-6324-4d53-ad4f-8cda48b30811"
    assert outbound["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
    reality = outbound["streamSettings"]["realitySettings"]
    assert reality["serverName"] == "yahoo.com"
    assert reality["publicKey"] == "WhVUiqgkpQOO10__jJjcevjRIIoWlZUdn-Tj3t5E2kY"
    assert reality["shortId"] == "123456"


def test_vless_websocket_tls():
    url = (
        "vless://d41d8cd9-8f00-b204-e980-0998ecf8427e@vless.cloud.com:443"
        "?security=tls"
        "&sni=vless.cloud.com"
        "&type=ws"
        "&path=%2Fwebsocket-path"
        "&host=vless.cloud.com"
        "&alpn=h2,http/1.1"
        "#WsNode"
    )
    cfg = parse_proxy_config(url)
    assert cfg.protocol == ProxyProtocol.VLESS
    assert cfg.network == "ws"
    assert cfg.security == "tls"
    assert cfg.ws_path == "/websocket-path"
    assert cfg.ws_host == "vless.cloud.com"
    assert cfg.alpn == ["h2", "http/1.1"]

    outbound = cfg.to_xray_outbound()
    assert outbound["streamSettings"]["network"] == "ws"
    assert outbound["streamSettings"]["security"] == "tls"
    assert outbound["streamSettings"]["wsSettings"]["path"] == "/websocket-path"
    assert outbound["streamSettings"]["wsSettings"]["headers"]["Host"] == "vless.cloud.com"


def test_invalid_configs():
    with pytest.raises(ValueError):
        parse_proxy_config("not_a_valid_proxy_string")

    with pytest.raises(ValueError):
        parse_proxy_config("127.0.0.1:invalid_port:user:pass")

    with pytest.raises(ValueError):
        parse_proxy_config("vless://@host:443")  # missing uuid
