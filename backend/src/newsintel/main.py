from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from newsintel import __version__
from newsintel.api.routes.acquisition import router as acquisition_router
from newsintel.api.routes.content import router as content_router
from newsintel.api.routes.dashboard import router as dashboard_router
from newsintel.api.routes.health import router as health_router
from newsintel.api.routes.sources import router as sources_router
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    app.state.settings = settings
    app.state.database = database
    yield
    await database.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="News Intelligence Platform API",
        version=__version__,
        description="Event-centric, evidence-backed news intelligence API",
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(acquisition_router, prefix="/api/v1")
    app.include_router(content_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(dashboard_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "newsintel.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
