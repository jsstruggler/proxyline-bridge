from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
from proxy_relay import ProxyManager
import uvicorn
from contextlib import asynccontextmanager
import sys

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
        
        return {"local_proxy": local_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_proxy")
async def get_proxy():
    """Returns the currently active local proxy URL, if any."""
    if not current_proxy_url:
        return {"local_proxy": None}
    return {"local_proxy": current_proxy_url}

if __name__ == "__main__":
    # If running as a compiled PyInstaller executable
    if getattr(sys, 'frozen', False):
        uvicorn.run(app, host="127.0.0.1", port=8000)
    else:
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
