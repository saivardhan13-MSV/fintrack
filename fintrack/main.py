import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from . import models  # noqa: F401  (registers tables on Base.metadata)
from .config import Settings, get_settings
from .database import Base, make_engine
from .errors import register_exception_handlers
from .routers import auth, budgets, categories, reports, subscriptions, transactions

logger = logging.getLogger("fintrack")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory: each call gets its own engine, which keeps tests isolated."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="FinTrack API",
        version="1.0.0",
        description="Personal finance & subscription tracker: transactions, CSV import, "
        "recurring-charge detection, budgets and spending analytics.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Tags each request with an id (reusing the caller's if sent) and logs its latency."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d in %.1fms request_id=%s",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response

    register_exception_handlers(app)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    for module in (auth, categories, transactions, subscriptions, budgets, reports):
        app.include_router(module.router, prefix="/api/v1")

    # The dashboard is a static single-page app that calls the API above.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def dashboard_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
