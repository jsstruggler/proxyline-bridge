from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
from proxy_relay import ProxyManager
import uvicorn
from contextlib import asynccontextmanager
import sys
import threading
import platform

is_mac = platform.system() == "Darwin"
if is_mac:
    import rumps
else:
    import pystray
    from PIL import Image, ImageDraw

# Global instances for UI
mac_app = None
win_app = None
win_status_text = "Status: Waiting for proxy..."

# Global proxy manager to manage lifecycle of proxies
proxy_manager = ProxyManager()
current_proxy_url = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the proxy manager
    await proxy_manager.__aenter__()
    yield
    # Shutdown: Clean up all proxies
    await proxy_manager.__aexit__(None, None, None)

app = FastAPI(title="Proxyline Bridge", lifespan=lifespan)

class ProxyConfig(BaseModel):
    config: str  # Expected format: ip:port:login:pass

@app.post("/set_proxy")
async def set_proxy(proxy: ProxyConfig):
    """
    Accepts a SOCKS5 config in the format ip:port:login:pass,
    starts a local unauthenticated HTTP proxy, and returns the local proxy URL.
    This local URL can be used directly in browser extensions.
    """
    global current_proxy_url
    
    parts = proxy.config.split(":")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="Invalid config format. Must be ip:port:login:pass")
    
    ip, port, login, password = parts
    # Construct upstream URL according to proxy-relay format
    upstream_url = f"socks5://{login}:{password}@{ip}:{port}"
    
    try:
        # Stop the old proxy if it exists to avoid port leaks
        if current_proxy_url:
            await proxy_manager.stop(current_proxy_url)
            current_proxy_url = None
            
        # Create new proxy, returning HTTP proxy for easier browser integration.
        local_url = await proxy_manager.create(upstream_url, local_type="http")
        current_proxy_url = local_url
        
        # Update Menu Bar app status
        if is_mac and mac_app:
            mac_app.title = "🌐 Active"
            try:
                # Assuming local_url looks like http://127.0.0.1:port
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
    # Uvicorn needs to be run without reload=True when in a thread
    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    if is_mac:
        class ProxylineBridgeApp(rumps.App):
            def __init__(self):
                super(ProxylineBridgeApp, self).__init__("🌐 Bridge")
                self.status_item = rumps.MenuItem("Status: Waiting for proxy...")
                self.port_item = rumps.MenuItem("Port: 8000")
                self.menu = [
                    self.status_item,
                    self.port_item,
                    None, # Separator
                ]
                
        mac_app = ProxylineBridgeApp()
        
        # Start the FastAPI server in a background thread
        api_thread = threading.Thread(target=run_uvicorn, daemon=True)
        api_thread.start()
        
        # Start the native macOS menu bar app loop in the main thread
        mac_app.run()
    else:
        def create_image():
            # Generate a simple blue square with "PB" text
            image = Image.new('RGB', (64, 64), color = (0, 102, 204))
            d = ImageDraw.Draw(image)
            d.text((20, 24), "PB", fill=(255, 255, 255))
            return image

        def on_quit(icon, item):
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem(lambda text: win_status_text, lambda icon, item: None),
            pystray.MenuItem("Port: 8000", lambda icon, item: None),
            pystray.MenuItem("Quit", on_quit)
        )
        
        win_app = pystray.Icon("proxyline-bridge", create_image(), "Proxyline Bridge", menu)
        
        # Start the FastAPI server in a background thread
        api_thread = threading.Thread(target=run_uvicorn, daemon=True)
        api_thread.start()
        
        # Start the native Windows/Linux system tray app loop in the main thread
        win_app.run()
