import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.analysis import router as analysis_router
from api.config import router as config_router
from api.interactive import router as interactive_router
from api.tasks import router as tasks_router
from api.trading import router as trading_router
from api.ws import router as ws_router
from api.workflow import router as workflow_router
from api.hot_tokens import router as hot_tokens_router
from api.polymarket import router as polymarket_router

from services.database import init_db
from services.config_store import get_config
from services.scheduler import (
    PolymarketScheduler,
    SignalScanScheduler,
    register,
    set_scheduler_instance,
)
from api.polymarket import _handle_cluster_signal
from services.sector_classifier import configure_proxy, get_classifier
from services.signal_scraper import BinanceSquareScraper
from services.ws_manager import manager

# --- Proxy setup from config ---
_config = get_config()
_proxy_url = _config.get("proxy_url", "")
if _proxy_url:
    os.environ["HTTP_PROXY"] = _proxy_url
    os.environ["HTTPS_PROXY"] = _proxy_url
    print(f"[main] Proxy configured: {_proxy_url}")

# Sector classifier uses the same proxy and warms up in the background
configure_proxy(_proxy_url)

_scraper = BinanceSquareScraper()


async def _ws_relay(event: str, payload: dict) -> None:
    """Adapter: scheduler calls (event, payload), ws_manager.broadcast expects {type, data}."""
    await manager.broadcast({"type": event, "data": payload})


_scheduler = SignalScanScheduler(_scraper, ws_broadcast=_ws_relay)
set_scheduler_instance(_scheduler)

_poly = PolymarketScheduler(signal_handler=_handle_cluster_signal)
register(_poly)


async def _warm_sector_classifier() -> None:
    try:
        await get_classifier().ensure_loaded()
    except Exception as _e:
        print(f"[main] sector classifier warmup failed: {_e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_warm_sector_classifier())
    await _scheduler.start()
    await _poly.start()
    yield
    await _scheduler.stop()
    await _poly.stop()


app = FastAPI(title="Browser Use Web Demo", lifespan=lifespan)

# Initialize database
init_db()

_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(config_router)
app.include_router(interactive_router)
app.include_router(tasks_router)
app.include_router(trading_router)
app.include_router(ws_router)
app.include_router(workflow_router)
app.include_router(hot_tokens_router)
app.include_router(polymarket_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files in production
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)