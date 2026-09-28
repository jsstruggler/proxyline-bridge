"""Xray core binary downloader and process runner."""

from __future__ import annotations

import atexit
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from typing import Any, Callable, Dict, Optional


def find_free_port() -> int:
    """Finds an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


class XrayManager:
    """Manages discovery and downloading of the Xray-core binary."""

    _download_lock = threading.Lock()

    @classmethod
    def get_asset_name(cls) -> str:
        """Determines the appropriate GitHub release asset for current OS and architecture."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "darwin":
            if "arm" in machine or "aarch" in machine:
                return "Xray-macos-arm64-v8a.zip"
            return "Xray-macos-64.zip"

        elif system == "windows":
            if "arm" in machine or "aarch" in machine:
                return "Xray-windows-arm64-v8a.zip"
            return "Xray-windows-64.zip"

        elif system == "linux":
            if "arm64" in machine or "aarch64" in machine:
                return "Xray-linux-arm64-v8a.zip"
            elif "arm" in machine:
                return "Xray-linux-arm32-v7a.zip"
            return "Xray-linux-64.zip"

        raise RuntimeError(f"Unsupported OS: {system} ({machine})")

    @classmethod
    def get_binary_filename(cls) -> str:
        return "xray.exe" if platform.system().lower() == "windows" else "xray"

    @classmethod
    def get_user_bin_dir(cls) -> str:
        """Returns the user-level bin directory for cached executables."""
        home = os.path.expanduser("~")
        bin_dir = os.path.join(home, ".proxyline-bridge", "bin")
        os.makedirs(bin_dir, exist_ok=True)
        return bin_dir

    @classmethod
    def find_binary(cls) -> Optional[str]:
        """
        Searches for the Xray binary in known locations:
        1. Environment variable PROXYLINE_XRAY_PATH or XRAY_PATH
        2. PyInstaller bundled directory (_MEIPASS)
        3. Adjacent to sys.executable (for frozen app bundles)
        4. Project local bin/ folder
        5. User cache directory (~/.proxyline-bridge/bin/)
        6. System PATH
        """
        bin_name = cls.get_binary_filename()

        # 1. Environment variable
        env_path = os.environ.get("PROXYLINE_XRAY_PATH") or os.environ.get("XRAY_PATH")
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return os.path.abspath(env_path)

        # 2. PyInstaller _MEIPASS
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                for candidate in [
                    os.path.join(meipass, "bin", bin_name),
                    os.path.join(meipass, bin_name),
                ]:
                    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        return candidate

            # 3. Next to executable
            exe_dir = os.path.dirname(sys.executable)
            candidate = os.path.join(exe_dir, bin_name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        # 4. Project local bin folder
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_candidate = os.path.join(project_root, "bin", bin_name)
        if os.path.isfile(local_candidate) and os.access(local_candidate, os.X_OK):
            return local_candidate

        # 5. User cache dir
        cached_path = os.path.join(cls.get_user_bin_dir(), bin_name)
        if os.path.isfile(cached_path) and os.access(cached_path, os.X_OK):
            return cached_path

        # 6. System PATH
        path_binary = shutil.which("xray") or shutil.which(bin_name)
        if path_binary:
            return path_binary

        return None

    @classmethod
    def download_binary(
        cls, status_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Downloads the Xray binary from the official GitHub releases.
        Thread-safe to prevent multiple parallel downloads.
        """
        with cls._download_lock:
            # Double-check if another thread just finished downloading
            existing = cls.find_binary()
            if existing:
                return existing

            asset_name = cls.get_asset_name()
            bin_name = cls.get_binary_filename()
            target_dir = cls.get_user_bin_dir()
            target_path = os.path.join(target_dir, bin_name)

            download_url = (
                f"https://github.com/XTLS/Xray-core/releases/latest/download/{asset_name}"
            )

            if status_callback:
                status_callback(f"Downloading Xray-core ({asset_name})...")

            req = urllib.request.Request(
                download_url, headers={"User-Agent": "ProxylineBridge"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()

            if status_callback:
                status_callback("Extracting Xray-core...")

            with zipfile.ZipFile(io.BytesIO(data)) as z:
                # Extract only the executable and optional geodata
                for member in z.namelist():
                    if member.endswith(bin_name) or member in ("geoip.dat", "geosite.dat"):
                        basename = os.path.basename(member)
                        out_path = os.path.join(target_dir, basename)
                        with z.open(member) as src, open(out_path, "wb") as dst:
                            dst.write(src.read())

            if not os.path.exists(target_path):
                raise RuntimeError(
                    f"Failed to find {bin_name} inside downloaded archive {asset_name}"
                )

            os.chmod(target_path, 0o755)

            if status_callback:
                status_callback("Xray-core ready.")

            return target_path

    @classmethod
    def ensure_binary(
        cls, status_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """Finds the Xray binary or downloads it if missing."""
        found = cls.find_binary()
        if found:
            return found
        return cls.download_binary(status_callback)


class XrayRunner:
    """Manages the execution and lifecycle of an Xray subprocess."""

    def __init__(self):
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.config_path: Optional[str] = None
        self.port: Optional[int] = None
        self.local_url: Optional[str] = None
        self._lock = threading.Lock()

        # Register cleanup on exit
        atexit.register(self.stop)

    def is_running(self) -> bool:
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def start(
        self,
        outbound_config: Dict[str, Any],
        local_port: Optional[int] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Starts an Xray instance configured with an unauthenticated local HTTP proxy inbound
        and the provided outbound configuration.
        Returns the local proxy URL (e.g. http://127.0.0.1:51234).
        """
        with self._lock:
            # Stop existing process if running
            self._stop_unlocked()

            xray_bin = XrayManager.ensure_binary(status_callback)

            port = local_port or find_free_port()

            full_config = {
                "log": {
                    "loglevel": "warning",
                },
                "inbounds": [
                    {
                        "tag": "http-in",
                        "port": port,
                        "listen": "127.0.0.1",
                        "protocol": "http",
                        "settings": {
                            "timeout": 300,
                            "allowTransparent": False,
                            "userLevel": 0,
                        },
                    }
                ],
                "outbounds": [
                    outbound_config,
                    {
                        "tag": "direct",
                        "protocol": "freedom",
                        "settings": {},
                    },
                ],
            }

            # Create temporary config file
            temp_fd, config_path = tempfile.mkstemp(
                prefix="proxyline_xray_", suffix=".json"
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2)

            self.config_path = config_path

            # Spawn Xray process
            creationflags = 0
            if platform.system() == "Windows":
                creationflags = 0x08000000  # CREATE_NO_WINDOW

            try:
                proc = subprocess.Popen(
                    [xray_bin, "run", "-c", config_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                )
                self.process = proc
                self.port = port
                self.local_url = f"http://127.0.0.1:{port}"

                # Allow Xray 200ms to initialize and detect immediate crashes
                time.sleep(0.2)
                if proc.poll() is not None:
                    stdout, stderr = proc.communicate(timeout=1)
                    out_msg = (stdout.decode("utf-8", errors="replace") + "\n" + stderr.decode("utf-8", errors="replace")).strip()
                    self._stop_unlocked()
                    raise RuntimeError(
                        f"Xray process terminated unexpectedly (code {proc.returncode}): {out_msg}"
                    )

                # Verify port is listening
                self._wait_for_port(port, timeout=2.0)

                return self.local_url

            except Exception as e:
                self._stop_unlocked()
                raise RuntimeError(f"Failed to start Xray: {e}") from e

    def _wait_for_port(self, port: int, timeout: float = 2.0) -> None:
        """Polls until localhost port accepts connections or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except (socket.error, ConnectionRefusedError):
                time.sleep(0.05)
        # Port didn't respond in time, but process is still running; allow proceeding

    def _stop_unlocked(self) -> None:
        """Internal helper to stop process without acquiring lock."""
        if self.process:
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=1.0)
            except Exception:
                pass
            finally:
                self.process = None

        if self.config_path and os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except Exception:
                pass
            finally:
                self.config_path = None

        self.port = None
        self.local_url = None

    def stop(self) -> None:
        """Stops the active Xray process and cleans up temporary config."""
        with self._lock:
            self._stop_unlocked()
