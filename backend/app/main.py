from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import run, stream, upload
from app.core.config import settings
from app.core.logging_config import configure_logging

configure_logging()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(run.router)
app.include_router(stream.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
