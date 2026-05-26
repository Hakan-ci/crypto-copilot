import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.mexc import router as mexc_router
from app.api.routes.trades import router as trades_router
from app.core.config import parse_cors_allowed_origins


def create_app(cors_allowed_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="MEXC Futures Trade Review Copilot",
        version="0.1.0",
        description=(
            "Read-only trade review, journaling, risk, and checklist assistant "
            "for MEXC Futures."
        ),
    )

    origins = (
        parse_cors_allowed_origins(os.getenv("CORS_ALLOWED_ORIGINS"))
        if cors_allowed_origins is None
        else cors_allowed_origins
    )
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(mexc_router)
    app.include_router(trades_router)
    return app


app = create_app()
