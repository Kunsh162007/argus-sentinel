"""
ARGUS Sentinel — Real-Time Intelligence Dashboard
FastAPI backend with WebSocket live streaming.
Serves the HTML dashboard and pushes intelligence updates in real time.
"""

import asyncio
import json
import logging
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator import ArgusOrchestrator
from config import CONFIG

logger = logging.getLogger("argus.dashboard")

app = FastAPI(
    title="ARGUS Sentinel",
    description="Autonomous Real-time Global Understanding System",
    version="1.0.0",
)

# In-memory report history
report_history: list[dict] = []
active_connections: list[WebSocket] = []


# ------------------------------------------------------------------ #
#  WebSocket connection manager                                        #
# ------------------------------------------------------------------ #

async def broadcast(message: dict):
    """Push a message to all connected WebSocket clients."""
    dead = []
    for ws in active_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        active_connections.remove(ws)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("WebSocket client connected. Total: %d", len(active_connections))

    # Send history on connect
    await websocket.send_json({"type": "history", "data": report_history[-20:]})

    try:
        while True:
            await asyncio.sleep(CONFIG.dashboard.ws_ping_interval)
            await websocket.send_json({"type": "ping", "ts": time.time()})
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info("WebSocket client disconnected")


# ------------------------------------------------------------------ #
#  REST endpoints                                                      #
# ------------------------------------------------------------------ #

class QueryRequest(BaseModel):
    query: str
    stream: bool = True


@app.post("/api/query")
async def run_query(req: QueryRequest):
    """
    Accept a query and immediately return 202, then run the pipeline as a
    background task so Render's 30-second request timeout is never hit.
    Results are pushed to the frontend via WebSocket.
    """
    await broadcast({
        "type": "status",
        "status": "running",
        "query": req.query,
        "ts": time.time(),
    })
    asyncio.create_task(_run_orchestrator(req.query))
    return JSONResponse(content={"status": "accepted", "query": req.query}, status_code=202)


async def _run_orchestrator(query: str):
    try:
        if not CONFIG.model.groq_api_key and not CONFIG.model.google_api_key:
            raise ValueError(
                "No LLM API key set. Add GROQ_API_KEY (free at console.groq.com) "
                "in Render → your service → Environment."
            )
        orchestrator = ArgusOrchestrator()
        await broadcast({"type": "status", "status": "agents_deployed", "query": query})
        report = await orchestrator.run(query)

        report_dict = report.to_dict()
        report_history.append(report_dict)

        if len(report_history) > CONFIG.dashboard.max_history_entries:
            report_history.pop(0)

        await broadcast({
            "type": "report",
            "data": report_dict,
            "alert": report.alert_triggered,
        })

    except Exception as e:
        logger.error("Query failed: %s", e)
        await broadcast({"type": "error", "message": str(e)})


@app.get("/api/history")
async def get_history(limit: int = 20):
    return JSONResponse(content=report_history[-limit:])


@app.get("/api/health")
async def health():
    return {"status": "ok", "connections": len(active_connections)}


# ------------------------------------------------------------------ #
#  Serve the HTML dashboard                                            #
# ------------------------------------------------------------------ #

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path) as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    uvicorn.run(
        "app:app",
        host=CONFIG.dashboard.host,
        port=CONFIG.dashboard.port,
        reload=False,
    )
