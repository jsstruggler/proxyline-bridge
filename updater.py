import os
import sys
import platform
import tempfile
import urllib.request
import subprocess
import threading

def get_expected_asset_name():
    is_mac = platform.system() == "Darwin"
    is_win = platform.system() == "Windows"
    is_linux = platform.system() == "Linux"
    arch = platform.machine().lower()
    
    if is_win:
        return "proxyline-bridge-windows.exe"
    elif is_linux:
        return "proxyline-bridge-linux"
    elif is_mac:
        if "arm" in arch or "aarch" in arch:
            return "proxyline-bridge-macos-m-series.dmg"
        else:
            return "proxyline-bridge-macos-intel.dmg"
    return None

def download_and_install_update(asset_url, status_callback=None):
    """
    Downloads the asset and spawns an OS-specific updater script.
    """
    try:
        # Check if running as compiled PyInstaller executable
        if not getattr(sys, 'frozen', False):
            if status_callback:
                status_callback("Error: Not running as compiled app")
            return
            
        exe_path = sys.executable
        
        if status_callback:
            status_callback("Status: Downloading update...")
            
        temp_dir = tempfile.gettempdir()
        asset_name = get_expected_asset_name()
        if not asset_name:
            if status_callback:
                status_callback("Error: Unknown platform")
            return
            
        downloaded_file = os.path.join(temp_dir, asset_name)
        
        req = urllib.request.Request(asset_url, headers={'User-Agent': 'ProxylineBridge'})
        with urllib.request.urlopen(req, timeout=300) as response, open(downloaded_file, 'wb') as out_file:
            out_file.write(response.read())
            
        if status_callback:
            status_callback("Status: Installing update...")
            
        is_mac = platform.system() == "Darwin"
        is_win = platform.system() == "Windows"
        is_linux = platform.system() == "Linux"
        
        if is_mac:
            # exe_path is typically /Applications/ProxylineBridge.app/Contents/MacOS/proxyline-bridge
            # We want the root .app path
            if "ProxylineBridge.app" in exe_path:
                app_path = exe_path[:exe_path.find("ProxylineBridge.app") + len("ProxylineBridge.app")]
            else:
                app_path = os.path.dirname(os.path.dirname(os.path.dirname(exe_path)))
                
            script_content = f"""#!/bin/bash
sleep 2
hdiutil attach "{downloaded_file}" -mountpoint "/Volumes/ProxylineUpdate" -nobrowse
rm -rf "{app_path}"
cp -R "/Volumes/ProxylineUpdate/ProxylineBridge.app" "{app_path}"
hdiutil detach "/Volumes/ProxylineUpdate" -force
open "{app_path}"
rm -f "{downloaded_file}"
rm -f "$0"
"""
            script_path = os.path.join(temp_dir, "update_proxyline.sh")
            with open(script_path, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
            
            subprocess.Popen([script_path], start_new_session=True)
            
        elif is_win:
            script_content = f"""@echo off
:loop
timeout /t 1 /nobreak >nul
del "{exe_path}"
if exist "{exe_path}" goto loop
copy /Y "{downloaded_file}" "{exe_path}"
start "" "{exe_path}"
del "{downloaded_file}"
del "%~f0"
"""
            script_path = os.path.join(temp_dir, "update_proxyline.bat")
            with open(script_path, "w") as f:
                f.write(script_content)
            
            # Use CREATE_NO_WINDOW for windows
            creationflags = 0x08000000 # CREATE_NO_WINDOW
            subprocess.Popen(["cmd.exe", "/c", script_path], creationflags=creationflags)
            
        elif is_linux:
            script_content = f"""#!/bin/bash
sleep 2
mv -f "{downloaded_file}" "{exe_path}"
chmod +x "{exe_path}"
nohup "{exe_path}" >/dev/null 2>&1 &
rm -f "$0"
"""
            script_path = os.path.join(temp_dir, "update_proxyline.sh")
            with open(script_path, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
            
            subprocess.Popen([script_path], start_new_session=True)

        # forcefully exit the python program to allow overwriting
        os._exit(0)

    except Exception as e:
        if status_callback:
            status_callback(f"Status: Update failed ({e})")
        print(f"Update error: {e}")

def trigger_update_in_background(asset_url, status_callback=None):
    thread = threading.Thread(
        target=download_and_install_update, 
        args=(asset_url, status_callback), 
        daemon=True
    )
    thread.start()
