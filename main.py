import sys
import threading
import tkinter as tk
from tkinter import messagebox
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from proxy_relay import ProxyManager
import uvicorn
from contextlib import asynccontextmanager

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

class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__()
        # Running in a separate thread, Uvicorn will automatically skip signal handlers
        self.config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
        self.server = uvicorn.Server(config=self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

class ProxylineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Proxyline Bridge")
        self.root.geometry("300x150")
        self.root.resizable(False, False)
        
        self.server_thread = None

        # UI Elements
        self.status_label = tk.Label(root, text="Status: Stopped", fg="red", font=("Arial", 16, "bold"))
        self.status_label.pack(pady=15)

        self.start_btn = tk.Button(root, text="Start Server", command=self.start_server, width=15)
        self.start_btn.pack(pady=2)

        self.stop_btn = tk.Button(root, text="Stop Server", command=self.stop_server, width=15, state=tk.DISABLED)
        self.stop_btn.pack(pady=2)
        
        # Ensure server stops when window is closed
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_server(self):
        if self.server_thread is None or not self.server_thread.is_alive():
            self.server_thread = ServerThread()
            self.server_thread.start()
            self.status_label.config(text="Status: Running", fg="green")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)

    def stop_server(self):
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.stop()
            # Wait briefly to let the thread shut down gracefully
            self.server_thread.join(timeout=2.0)
            self.status_label.config(text="Status: Stopped", fg="red")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def on_closing(self):
        self.stop_server()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    
    # On macOS, bring the window to the front automatically
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    
    app_gui = ProxylineApp(root)
    root.mainloop()
