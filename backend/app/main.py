import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.crypto_basket import router as crypto_basket_router
from app.api.routes.health import router as health_router
from app.api.routes.mexc import router as mexc_router
from app.api.routes.trades import router as trades_router
from app.api.routes.trading_plan import router as trading_plan_router
from app.core.config import get_settings, parse_cors_allowed_origins
from app.db.session import get_sessionmaker
from app.services.crypto_basket_scheduler import CryptoBasketScheduler


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
    app.include_router(crypto_basket_router)
    app.include_router(trading_plan_router)
    app.include_router(trades_router)

    if _env_bool("CRYPTO_BASKET_SYNC_ENABLED"):
        _register_crypto_basket_scheduler(app)
    return app


def _register_crypto_basket_scheduler(app: FastAPI) -> None:
    @app.on_event("startup")
    async def start_crypto_basket_scheduler() -> None:
        settings = get_settings()
        if not settings.crypto_basket_sync_enabled:
            return
        scheduler = CryptoBasketScheduler(
            settings=settings,
            session_factory=get_sessionmaker(),
        )
        app.state.crypto_basket_scheduler = scheduler
        scheduler.start()

    @app.on_event("shutdown")
    async def stop_crypto_basket_scheduler() -> None:
        scheduler = getattr(app.state, "crypto_basket_scheduler", None)
        if scheduler is not None:
            await scheduler.stop()


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


app = create_app()
