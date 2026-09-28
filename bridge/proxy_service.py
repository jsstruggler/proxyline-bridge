"""Unified proxy bridge service coordinating proxy-relay and Xray-core backends."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional
from proxy_relay import ProxyManager

from bridge.config_parser import (
    ParsedProxyConfig,
    ProxyProtocol,
    parse_proxy_config,
)
from bridge.xray_manager import XrayRunner


class ProxyBridgeService:
    """
    Coordinates upstream proxy routing and local HTTP proxy endpoints.
    Uses proxy-relay for SOCKS5 and HTTP.
    Uses Xray-core for Shadowsocks and VLESS.
    """

    def __init__(self, on_status_change: Optional[Callable[[str, Optional[str]], None]] = None):
        self.proxy_manager = ProxyManager()
        self.xray_runner = XrayRunner()

        self.current_local_url: Optional[str] = None
        self.current_protocol: Optional[ProxyProtocol] = None
        self.current_backend: Optional[str] = None  # "proxy-relay" | "xray"
        self.current_tag: Optional[str] = None

        self.on_status_change = on_status_change
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        """Initializes underlying managers upon application startup."""
        await self.proxy_manager.__aenter__()

    async def shutdown(self) -> None:
        """Stops active proxies and cleans up background tasks upon application shutdown."""
        await self.stop_proxy()
        try:
            await self.proxy_manager.__aexit__(None, None, None)
        except Exception:
            pass

    async def stop_proxy(self) -> None:
        """Stops whatever proxy backend is currently running."""
        async with self._lock:
            await self._stop_internal()

    async def _stop_internal(self) -> None:
        if self.current_local_url:
            if self.current_backend == "proxy-relay":
                try:
                    await self.proxy_manager.stop(self.current_local_url)
                except Exception as e:
                    print(f"Warning: error stopping proxy-relay: {e}")
            elif self.current_backend == "xray":
                try:
                    await asyncio.to_thread(self.xray_runner.stop)
                except Exception as e:
                    print(f"Warning: error stopping Xray: {e}")

        self.current_local_url = None
        self.current_protocol = None
        self.current_backend = None
        self.current_tag = None

        if self.on_status_change:
            try:
                self.on_status_change("Status: Waiting for proxy...", None)
            except Exception:
                pass

    async def set_proxy(
        self,
        config: str,
        protocol: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Parses proxy configuration, stops old proxy, starts the appropriate backend,
        and returns local HTTP proxy details.
        """
        parsed: ParsedProxyConfig = parse_proxy_config(config, protocol)

        async with self._lock:
            # Stop existing active proxy
            await self._stop_internal()

            local_url: str

            if parsed.protocol in (ProxyProtocol.VLESS, ProxyProtocol.SHADOWSOCKS):
                # Run with Xray-core
                outbound = parsed.to_xray_outbound()
                local_url = await asyncio.to_thread(
                    self.xray_runner.start, outbound, None, status_callback
                )
                self.current_backend = "xray"
            else:
                # SOCKS5 or HTTP -> proxy-relay
                upstream_url = parsed.to_upstream_url()
                local_url = await self.proxy_manager.create(
                    upstream_url, local_type="http"
                )
                self.current_backend = "proxy-relay"

            self.current_local_url = local_url
            self.current_protocol = parsed.protocol
            self.current_tag = parsed.tag

            # Notify status callback
            if self.on_status_change:
                try:
                    port_str = local_url.split(":")[-1]
                    proto_name = parsed.protocol.value.upper()
                    status_msg = f"Status: Proxy active (port {port_str}, {proto_name})"
                    self.on_status_change(status_msg, proto_name)
                except Exception:
                    pass

            return {
                "local_proxy": local_url,
                "protocol": parsed.protocol.value,
                "tag": parsed.tag,
            }

    async def get_proxy(self) -> Dict[str, Any]:
        """Returns the currently active local proxy and protocol info."""
        async with self._lock:
            if not self.current_local_url:
                return {"local_proxy": None, "protocol": None}
            return {
                "local_proxy": self.current_local_url,
                "protocol": (
                    self.current_protocol.value if self.current_protocol else None
                ),
                "tag": self.current_tag,
            }
