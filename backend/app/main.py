from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .clob_ws import clob_stream
from .config import settings
from .hub import manager
from .store import market_store


class ScannerControl(BaseModel):
    enabled: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    poll_task = asyncio.create_task(market_store.run_poll_loop())
    crypto_task = asyncio.create_task(market_store.run_crypto_hot_loop())
    clob_scan_task = asyncio.create_task(market_store.run_clob_scan_loop())
    clob_task = asyncio.create_task(clob_stream.run())
    yield
    poll_task.cancel()
    crypto_task.cancel()
    clob_scan_task.cancel()
    clob_task.cancel()


app = FastAPI(title="PolyMonitor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <title>PolyMonitor 后端已启动</title>
        <style>
          body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #080d13; color: #eef4ff; }
          main { max-width: 760px; margin: 80px auto; padding: 32px; border: 1px solid #223044; border-radius: 8px; background: #111821; }
          a { color: #8fa1ff; }
          code { background: #192333; padding: 2px 6px; border-radius: 4px; }
          li { margin: 10px 0; }
        </style>
      </head>
      <body>
        <main>
          <h1>PolyMonitor 后端已启动</h1>
          <p>这是后端服务地址，不是前端页面。请打开前端监控台：</p>
          <p><a href="http://127.0.0.1:5173/">http://127.0.0.1:5173/</a></p>
          <h2>可用接口</h2>
          <ul>
            <li><a href="/api/health"><code>/api/health</code></a>：健康检查</li>
            <li><a href="/api/markets"><code>/api/markets</code></a>：筛选后的市场列表</li>
            <li><code>/ws/market</code>：前端实时 WebSocket</li>
          </ul>
        </main>
      </body>
    </html>
    """


@app.get("/api/markets")
async def markets():
    return await market_store.list_markets()


@app.get("/api/events")
async def events():
    return list(manager.events)


@app.get("/api/status")
async def status():
    connection = _effective_connection_status()
    return {
        "scanning_enabled": market_store.scanning_enabled,
        "last_scan_started_at": market_store.last_scan_started_at,
        "last_scan_completed_at": market_store.last_scan_completed_at,
        "last_clob_scan_completed_at": market_store.last_clob_scan_completed_at,
        "connection": connection,
    }


@app.post("/api/scanner")
async def set_scanner(control: ScannerControl):
    await market_store.set_scanning_enabled(control.enabled)
    return {
        "scanning_enabled": market_store.scanning_enabled,
        "connection": _effective_connection_status(),
    }


@app.websocket("/ws/market")
async def market_ws(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json({"type": "markets_snapshot", "data": [m.model_dump(mode="json") for m in await market_store.list_markets()]})
    await websocket.send_json({"type": "events_snapshot", "data": list(manager.events)})
    await websocket.send_json({"type": "connection_status", "data": _effective_connection_status()})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "focus_markets":
                await clob_stream.set_focus_markets(message.get("market_ids") or [])
    except (WebSocketDisconnect, RuntimeError):
        await manager.disconnect(websocket)


def _effective_connection_status() -> dict:
    connection = dict(manager.connection_status)
    if not market_store.scanning_enabled:
        connection.update(
            {
                "gamma": "paused",
                "scanner": "paused",
                "crypto_hot": "paused",
                "clob_scan": "paused",
            }
        )
        if connection.get("clob") in {None, "unknown", "reconnecting", "error"}:
            connection["clob"] = "paused"
        connection.pop("error", None)
        return connection
    now = datetime.now(timezone.utc)
    if market_store.last_scan_completed_at:
        gamma_age = (now - market_store.last_scan_completed_at).total_seconds()
        if gamma_age <= settings.poll_interval_seconds * 2 + 30:
            connection["gamma"] = "ok"
    if market_store.last_clob_scan_completed_at:
        clob_age = (now - market_store.last_clob_scan_completed_at).total_seconds()
        if clob_age <= settings.clob_scan_interval_seconds * 3 + 15:
            connection["clob"] = "connected"
            connection["clob_scan"] = "ok"
    if not any(value in {"error", "reconnecting"} for value in connection.values()):
        connection.pop("error", None)
    return connection
