from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
from proxy_relay import ProxyManager
import uvicorn
from contextlib import asynccontextmanager
import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
import threading
import platform
import urllib.request
import json
import webbrowser
import updater

is_mac = platform.system() == "Darwin"
if is_mac:
    import rumps
else:
    import pystray
    from PIL import Image, ImageDraw

mac_app = None
win_app = None
win_status_text = "Status: Waiting for proxy..."

proxy_manager = ProxyManager()
current_proxy_url = None

CURRENT_VERSION = "1.0.9"
GITHUB_REPO = "jsstruggler/proxyline-bridge"
update_url = None

def check_for_updates():
    global update_url
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={'User-Agent': 'ProxylineBridge'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            latest_version = data.get("tag_name", "").lstrip("v")
            
            asset_url = None
            expected_name = updater.get_expected_asset_name()
            for asset in data.get("assets", []):
                if asset.get("name") == expected_name:
                    asset_url = asset.get("browser_download_url")
                    break
            
            if not asset_url:
                asset_url = data.get("html_url", "")
            
            if latest_version and latest_version != CURRENT_VERSION:
                try:
                    current_parts = [int(x) for x in CURRENT_VERSION.split(".")]
                    latest_parts = [int(x) for x in latest_version.split(".")]
                    if latest_parts > current_parts:
                        update_url = asset_url
                except ValueError:
                    if latest_version != CURRENT_VERSION:
                        update_url = asset_url
    except Exception as e:
        print(f"Update check failed: {e}")

    if update_url:
        if is_mac and mac_app:
            def on_update_click(sender):
                if update_url.endswith(".dmg") or update_url.endswith(".exe") or update_url.endswith("-linux"):
                    def mac_status_cb(msg):
                        mac_app.status_item.title = msg
                    updater.trigger_update_in_background(update_url, mac_status_cb)
                else:
                    webbrowser.open(update_url)
            update_item = rumps.MenuItem("📥 Install Update", callback=on_update_click)
            mac_app.menu.add(update_item)
        elif not is_mac and win_app:
            win_app.update_menu()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await proxy_manager.__aenter__()
    yield
    await proxy_manager.__aexit__(None, None, None)

app = FastAPI(title=f"Proxyline Bridge v{CURRENT_VERSION}", lifespan=lifespan)

class ProxyConfig(BaseModel):
    config: str 

@app.post("/set_proxy")
async def set_proxy(proxy: ProxyConfig):

    global current_proxy_url
    
    parts = proxy.config.split(":")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid config format. Must be ip:port:login:pass")
    
    ip, port, login, password = parts
    upstream_url = f"socks5://{login}:{password}@{ip}:{port}"
    
    try:
        if current_proxy_url:
            await proxy_manager.stop(current_proxy_url)
            current_proxy_url = None
            
        local_url = await proxy_manager.create(upstream_url, local_type="http")
        current_proxy_url = local_url
        
        if is_mac and mac_app:
            mac_app.title = "🌐 Active"
            try:
                port_str = local_url.split(":")[-1]
                mac_app.status_item.title = f"Status: Proxy active (port {port_str})"
            except:
                mac_app.status_item.title = "Status: Proxy active"
        elif not is_mac and win_app:
            win_app.title = "Proxyline Bridge (Active)"
            try:
                port_str = local_url.split(":")[-1]
                global win_status_text
                win_status_text = f"Status: Proxy active (port {port_str})"
                win_app.update_menu()
            except:
                win_status_text = "Status: Proxy active"
                win_app.update_menu()
        
        return {"local_proxy": local_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_proxy")
async def get_proxy():
    """Returns the currently active local proxy URL, if any."""
    if not current_proxy_url:
        return {"local_proxy": None}
    return {"local_proxy": current_proxy_url}

def run_uvicorn():
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)

if __name__ == "__main__":
    if is_mac:
        class ProxylineBridgeApp(rumps.App):
            def __init__(self):
                super(ProxylineBridgeApp, self).__init__(f"🌐 Bridge v{CURRENT_VERSION}")
                self.status_item = rumps.MenuItem("Status: Waiting for proxy...")
                self.port_item = rumps.MenuItem("Port: 8000")
                self.menu = [
                    self.status_item,
                    self.port_item,
                    None,
                ]
                
        mac_app = ProxylineBridgeApp()
        
        api_thread = threading.Thread(target=run_uvicorn, daemon=True)
        api_thread.start()
        
        threading.Thread(target=check_for_updates, daemon=True).start()
        
        mac_app.run()
    else:
        def create_image():
            image = Image.new('RGB', (64, 64), color = (0, 102, 204))
            d = ImageDraw.Draw(image)
            d.text((20, 24), "PB", fill=(255, 255, 255))
            return image

        def on_quit(icon, item):
            icon.stop()
            
        def on_update_item_click(icon, item):
            if update_url:
                if update_url.endswith(".dmg") or update_url.endswith(".exe") or update_url.endswith("-linux"):
                    def win_status_cb(msg):
                        global win_status_text
                        win_status_text = msg
                        if win_app:
                            win_app.update_menu()
                    updater.trigger_update_in_background(update_url, win_status_cb)
                else:
                    webbrowser.open(update_url)

        menu = pystray.Menu(
            pystray.MenuItem(lambda text: win_status_text, lambda icon, item: None),
            pystray.MenuItem("Port: 8000", lambda icon, item: None),
            pystray.MenuItem("📥 Install Update", on_update_item_click, visible=lambda item: update_url is not None),
            pystray.MenuItem("Quit", on_quit)
        )
        
        win_app = pystray.Icon("proxyline-bridge", create_image(), f"Proxyline Bridge v{CURRENT_VERSION}", menu)
        
        api_thread = threading.Thread(target=run_uvicorn, daemon=True)
        api_thread.start()
        
        threading.Thread(target=check_for_updates, daemon=True).start()
        
        win_app.run()
