"""FastAPI app: mounts /api/v1 and serves the single-file web UI at / (spec sections 30, 34)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .api.v1 import router as api_v1
from .db import init_db
from .scheduler import start_background_sync

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()               # create tables + stamp schema_version before serving
    start_background_sync()  # refresh on startup (if stale) then every 4h, in a daemon thread
    yield


app = FastAPI(title="Job Radar", version="0.1.0", lifespan=lifespan)
app.include_router(api_v1)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")
