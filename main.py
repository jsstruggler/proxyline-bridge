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

# Global instance of our mac app to update the status
mac_app = None# Global proxy manager to manage lifecycle of proxies
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
        # Run standard console server on non-macOS platforms
        run_uvicorn()
