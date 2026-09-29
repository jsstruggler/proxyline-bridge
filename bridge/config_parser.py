"""Proxy configuration parser supporting SOCKS5, HTTP, Shadowsocks, and VLESS."""

from __future__ import annotations

import base64
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse
from pydantic import BaseModel, Field


class ProxyProtocol(str, Enum):
    SOCKS5 = "socks5"
    HTTP = "http"
    SHADOWSOCKS = "shadowsocks"
    VLESS = "vless"


KNOWN_SHADOWSOCKS_METHODS = {
    # AEAD Ciphers
    "aes-128-gcm",
    "aes-192-gcm",
    "aes-256-gcm",
    "chacha20-ietf-poly1305",
    "chacha20-poly1305",
    "xchacha20-ietf-poly1305",
    # Shadowsocks 2022
    "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
    # Stream Ciphers (Legacy)
    "aes-128-cfb",
    "aes-192-cfb",
    "aes-256-cfb",
    "aes-128-ctr",
    "aes-192-ctr",
    "aes-256-ctr",
    "rc4-md5",
    "none",
}


def safe_b64decode(s: str) -> str:
    """Safely decodes base64 string handling missing padding and URL-safe characters."""
    s = s.strip().replace("-", "+").replace("_", "/")
    # Add padding if needed
    remainder = len(s) % 4
    if remainder > 0:
        s += "=" * (4 - remainder)
    decoded_bytes = base64.b64decode(s.encode("ascii"))
    return decoded_bytes.decode("utf-8", errors="replace")


class ParsedProxyConfig(BaseModel):
    """Structured representation of a parsed proxy configuration."""

    protocol: ProxyProtocol
    host: str
    port: int
    tag: Optional[str] = None

    # SOCKS5 / HTTP credentials
    username: Optional[str] = None
    password: Optional[str] = None

    # Shadowsocks settings
    method: Optional[str] = None

    # VLESS settings
    uuid: Optional[str] = None
    flow: Optional[str] = None
    encryption: Optional[str] = "none"
    network: Optional[str] = "tcp"  # tcp, ws, grpc, http, splithttp, kcp
    security: Optional[str] = "none"  # none, tls, reality

    # TLS / Reality settings
    sni: Optional[str] = None
    fingerprint: Optional[str] = "chrome"
    alpn: Optional[List[str]] = None
    allow_insecure: bool = False

    header_type: Optional[str] = None

    # Reality specific settings
    public_key: Optional[str] = None
    short_id: Optional[str] = None
    spider_x: Optional[str] = "/"

    # WebSocket specific settings
    ws_path: Optional[str] = None
    ws_host: Optional[str] = None

    # gRPC specific settings
    grpc_service_name: Optional[str] = None
    grpc_multi_mode: bool = False

    # Raw custom outbound / config overrides if supplied
    custom_outbound: Optional[Dict[str, Any]] = None

    def to_upstream_url(self) -> str:
        """Converts to upstream URL format expected by proxy-relay (for socks5/http)."""
        scheme = self.protocol.value
        auth = ""
        if self.username or self.password:
            user = self.username or ""
            pwd = self.password or ""
            auth = f"{user}:{pwd}@"
        return f"{scheme}://{auth}{self.host}:{self.port}"

    def to_xray_outbound(self) -> Dict[str, Any]:
        """Generates an Xray outbound configuration dictionary."""
        if self.custom_outbound:
            return self.custom_outbound

        tag = self.tag or "proxy"

        if self.protocol == ProxyProtocol.VLESS:
            outbound: Dict[str, Any] = {
                "tag": tag,
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": self.host,
                            "port": self.port,
                            "users": [
                                {
                                    "id": self.uuid,
                                    "encryption": self.encryption or "none",
                                    "level": 0,
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": self.network or "tcp",
                    "security": self.security or "none",
                },
            }

            if self.flow:
                outbound["settings"]["vnext"][0]["users"][0]["flow"] = self.flow

            stream_settings = outbound["streamSettings"]
            sec = self.security or "none"

            if sec == "reality":
                stream_settings["realitySettings"] = {
                    "show": False,
                    "fingerprint": self.fingerprint or "chrome",
                    "serverName": self.sni or self.host,
                    "publicKey": self.public_key or "",
                    "shortId": self.short_id or "",
                    "spiderX": self.spider_x or "/",
                }
            elif sec == "tls":
                tls_settings: Dict[str, Any] = {
                    "allowInsecure": self.allow_insecure,
                    "serverName": self.sni or self.host,
                    "fingerprint": self.fingerprint or "chrome",
                }
                if self.alpn:
                    tls_settings["alpn"] = self.alpn
                stream_settings["tlsSettings"] = tls_settings

            net = self.network or "tcp"
            if net == "ws":
                ws_settings: Dict[str, Any] = {
                    "path": self.ws_path or "/",
                }
                if self.ws_host:
                    ws_settings["headers"] = {"Host": self.ws_host}
                stream_settings["wsSettings"] = ws_settings
            elif net == "grpc":
                stream_settings["grpcSettings"] = {
                    "serviceName": self.grpc_service_name or "",
                    "multiMode": self.grpc_multi_mode,
                }
            elif net == "tcp" and self.header_type == "http" and sec != "reality":
                # HTTP header obfuscation on raw TCP (only when explicitly requested and not Reality)
                stream_settings["tcpSettings"] = {
                    "header": {
                        "type": "http",
                        "request": {
                            "path": [self.ws_path or "/"],
                            "headers": {"Host": [self.ws_host or self.host]},
                        },
                    }
                }

            return outbound

        elif self.protocol == ProxyProtocol.SHADOWSOCKS:
            return {
                "tag": tag,
                "protocol": "shadowsocks",
                "settings": {
                    "servers": [
                        {
                            "address": self.host,
                            "port": self.port,
                            "method": self.method or "aes-256-gcm",
                            "password": self.password or "",
                            "level": 0,
                        }
                    ]
                },
            }

        elif self.protocol == ProxyProtocol.SOCKS5:
            server_entry: Dict[str, Any] = {
                "address": self.host,
                "port": self.port,
            }
            if self.username or self.password:
                server_entry["users"] = [
                    {
                        "user": self.username or "",
                        "pass": self.password or "",
                        "level": 0,
                    }
                ]
            return {
                "tag": tag,
                "protocol": "socks",
                "settings": {
                    "servers": [server_entry],
                },
            }

        elif self.protocol == ProxyProtocol.HTTP:
            server_entry = {
                "address": self.host,
                "port": self.port,
            }
            if self.username or self.password:
                server_entry["users"] = [
                    {
                        "user": self.username or "",
                        "pass": self.password or "",
                    }
                ]
            return {
                "tag": tag,
                "protocol": "http",
                "settings": {
                    "servers": [server_entry],
                },
            }

        raise ValueError(f"Unsupported protocol for Xray outbound: {self.protocol}")


def parse_vless_url(url_str: str) -> ParsedProxyConfig:
    """
    Parses standard VLESS URL into ParsedProxyConfig.
    Format: vless://uuid@host:port?query#tag
    """
    parsed = urlparse(url_str)
    if parsed.scheme.lower() != "vless":
        raise ValueError(f"Invalid scheme for VLESS: {parsed.scheme}")

    uuid = unquote(parsed.username or "")
    if not uuid:
        raise ValueError("Missing UUID in VLESS URL")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("Missing host in VLESS URL")

    port = parsed.port
    if not port or not (1 <= port <= 65535):
        raise ValueError(f"Invalid or missing port in VLESS URL: {port}")

    tag = unquote(parsed.fragment) if parsed.fragment else None

    # Parse query parameters
    query_params = parse_qs(parsed.query)

    def get_param(name: str, default: Optional[str] = None) -> Optional[str]:
        val = query_params.get(name)
        if val and len(val) > 0:
            return unquote(val[0])
        return default

    network = get_param("type", get_param("network", "tcp")).lower()
    security = get_param("security", "none").lower()
    flow = get_param("flow")
    encryption = get_param("encryption", "none")

    # TLS / Reality settings
    sni = get_param("sni", get_param("serverName"))
    fingerprint = get_param("fp", get_param("fingerprint", "chrome"))
    alpn_str = get_param("alpn")
    alpn = [x.strip() for x in alpn_str.split(",") if x.strip()] if alpn_str else None
    allow_insecure_val = get_param("allowInsecure", "0").lower()
    allow_insecure = allow_insecure_val in ("1", "true", "yes")

    # Reality settings
    public_key = get_param("pbk", get_param("publicKey"))
    short_id = get_param("sid", get_param("shortId"))
    spider_x = get_param("spx", get_param("spiderX", "/"))
    header_type = get_param("headerType")

    # WebSocket settings
    ws_path = get_param("path", "/" if network == "ws" else None)
    ws_host = get_param("host")

    # gRPC settings
    grpc_service_name = get_param("serviceName")
    grpc_multi_mode = get_param("mode", "").lower() == "multi"

    return ParsedProxyConfig(
        protocol=ProxyProtocol.VLESS,
        host=host,
        port=port,
        tag=tag,
        uuid=uuid,
        flow=flow,
        encryption=encryption,
        network=network,
        security=security,
        sni=sni,
        fingerprint=fingerprint,
        alpn=alpn,
        allow_insecure=allow_insecure,
        public_key=public_key,
        short_id=short_id,
        spider_x=spider_x,
        header_type=header_type,
        ws_path=ws_path,
        ws_host=ws_host,
        grpc_service_name=grpc_service_name,
        grpc_multi_mode=grpc_multi_mode,
    )


def parse_shadowsocks_url(url_str: str) -> ParsedProxyConfig:
    """
    Parses Shadowsocks URL into ParsedProxyConfig.
    Supports SIP002 (ss://base64(method:password)@host:port#tag),
    Legacy base64 (ss://base64(method:password@host:port)#tag),
    and plain (ss://method:password@host:port#tag).
    """
    # Remove prefix
    raw = url_str[len("ss://"):]

    # Extract tag/fragment
    tag = None
    if "#" in raw:
        raw, tag_part = raw.split("#", 1)
        tag = unquote(tag_part)

    # Check for query parameters (e.g., ?plugin=...)
    query_params: Dict[str, List[str]] = {}
    if "?" in raw:
        raw, query_str = raw.split("?", 1)
        query_params = parse_qs(query_str)

    method: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None

    if "@" in raw:
        # SIP002 or Plain format: user_info@host:port
        user_info, host_port = raw.rsplit("@", 1)
        if ":" in user_info:
            # Plain method:password
            method, password = user_info.split(":", 1)
        else:
            # Base64 encoded method:password
            decoded = safe_b64decode(user_info)
            if ":" in decoded:
                method, password = decoded.split(":", 1)
            else:
                raise ValueError(f"Invalid Shadowsocks userinfo: {user_info}")

        if ":" in host_port:
            host, port_str = host_port.rsplit(":", 1)
            port = int(port_str)
        else:
            raise ValueError(f"Missing port in Shadowsocks host:port: {host_port}")
    else:
        # Legacy format: ss://base64(method:password@host:port)
        decoded = safe_b64decode(raw)
        if "@" in decoded:
            user_info, host_port = decoded.rsplit("@", 1)
            if ":" in user_info:
                method, password = user_info.split(":", 1)
            if ":" in host_port:
                host, port_str = host_port.rsplit(":", 1)
                port = int(port_str)
        else:
            raise ValueError(f"Could not parse legacy Shadowsocks URL: {url_str}")

    if not host or not port or not method:
        raise ValueError(f"Incomplete Shadowsocks URL: {url_str}")

    method = unquote(method).strip()
    password = unquote(password or "")
    host = unquote(host).strip()

    return ParsedProxyConfig(
        protocol=ProxyProtocol.SHADOWSOCKS,
        host=host,
        port=port,
        tag=tag,
        method=method,
        password=password,
    )


def parse_proxy_config(
    config: str, protocol: Optional[str] = None
) -> ParsedProxyConfig:
    """
    Main parser entrypoint. Accepts URLs or colon-separated strings.
    Auto-detects protocol if not explicitly given.
    """
    config_clean = config.strip()
    proto_hint = protocol.lower().strip() if protocol else None

    # Check if raw JSON config
    if config_clean.startswith("{") and config_clean.endswith("}"):
        try:
            data = json.loads(config_clean)
            if "outbounds" in data:
                # Direct full Xray config, extract primary outbound
                primary = data["outbounds"][0]
                p_type = primary.get("protocol", "custom")
                proto_enum = ProxyProtocol.VLESS if p_type == "vless" else (
                    ProxyProtocol.SHADOWSOCKS if p_type == "shadowsocks" else ProxyProtocol.SOCKS5
                )
                return ParsedProxyConfig(
                    protocol=proto_enum,
                    host="custom",
                    port=0,
                    custom_outbound=primary,
                )
        except Exception:
            pass

    # Check explicit URI schemes
    if config_clean.startswith("vless://"):
        return parse_vless_url(config_clean)

    if config_clean.startswith("ss://"):
        return parse_shadowsocks_url(config_clean)

    if config_clean.startswith("socks5://") or config_clean.startswith("socks5h://"):
        parsed = urlparse(config_clean)
        return ParsedProxyConfig(
            protocol=ProxyProtocol.SOCKS5,
            host=parsed.hostname or "",
            port=parsed.port or 1080,
            username=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
            tag=unquote(parsed.fragment) if parsed.fragment else None,
        )

    if config_clean.startswith("http://") or config_clean.startswith("https://"):
        parsed = urlparse(config_clean)
        return ParsedProxyConfig(
            protocol=ProxyProtocol.HTTP,
            host=parsed.hostname or "",
            port=parsed.port or (443 if parsed.scheme == "https" else 80),
            username=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
            tag=unquote(parsed.fragment) if parsed.fragment else None,
        )

    # Colon-separated format: host:port:part3:part4
    parts = config_clean.split(":")
    if len(parts) == 4:
        host, port_str, p3, p4 = parts
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"Port must be an integer, got: {port_str}")

        # Check if Shadowsocks protocol requested or method detected
        is_ss = False
        if proto_hint in ("shadowsocks", "ss"):
            is_ss = True
        elif p3.lower() in KNOWN_SHADOWSOCKS_METHODS or p4.lower() in KNOWN_SHADOWSOCKS_METHODS:
            is_ss = True

        if is_ss:
            if p4.lower() in KNOWN_SHADOWSOCKS_METHODS:
                # host:port:password:method
                method = p4.lower()
                password = p3
            else:
                # host:port:method:password
                method = p3.lower()
                password = p4

            return ParsedProxyConfig(
                protocol=ProxyProtocol.SHADOWSOCKS,
                host=host,
                port=port,
                method=method,
                password=password,
            )
        else:
            # Default to SOCKS5 (standard Proxyline format)
            return ParsedProxyConfig(
                protocol=ProxyProtocol.SOCKS5,
                host=host,
                port=port,
                username=p3,
                password=p4,
            )

    elif len(parts) == 2:
        host, port_str = parts
        port = int(port_str)
        proto = ProxyProtocol.SOCKS5
        if proto_hint == "http":
            proto = ProxyProtocol.HTTP
        elif proto_hint in ("shadowsocks", "ss"):
            proto = ProxyProtocol.SHADOWSOCKS

        return ParsedProxyConfig(
            protocol=proto,
            host=host,
            port=port,
        )

    raise ValueError(
        f"Unrecognized proxy configuration format. "
        f"Supported formats: vless://..., ss://..., socks5://..., http://..., or ip:port:login:pass"
    )
