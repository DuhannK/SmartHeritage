"""SmartHeritage API.

Çalıştırma:  uvicorn app.main:app --reload
Belgeler:    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import records, risk, seismic, structures

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SmartHeritage",
    description=(
        "Dijital İkiz Tabanlı Akıllı Kültürel Miras İzleme ve Bakım Sistemi. "
        "Çıktılar karar destek amaçlıdır; restorasyon talimatı değildir."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

for module in (structures, records, seismic, risk):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["Sistem"])
def health():
    return {"status": "ok"}


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
