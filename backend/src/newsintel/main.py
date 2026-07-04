from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from starlette.middleware.cors import CORSMiddleware

from newsintel import __version__
from newsintel.api.routes.access_admin import router as access_admin_router
from newsintel.api.routes.acquisition import router as acquisition_router
from newsintel.api.routes.auth import router as auth_router
from newsintel.api.routes.content import router as content_router
from newsintel.api.routes.dashboard import router as dashboard_router
from newsintel.api.routes.health import router as health_router
from newsintel.api.routes.pages import router as pages_router
from newsintel.api.routes.sources import router as sources_router
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https: data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


async def _security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response: Response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if request.url.path.startswith(("/app", "/admin", "/news-sources", "/api/")):
        response.headers.setdefault("Cache-Control", "private, no-store")
    return response


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
    settings = get_settings()
    app = FastAPI(
        title="News Intelligence Platform API",
        version=__version__,
        description="Event-centric, evidence-backed news intelligence API",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
        openapi_url=None if settings.environment == "production" else "/openapi.json",
        lifespan=lifespan,
    )
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        )
    app.middleware("http")(_security_headers)
    app.include_router(pages_router)
    app.include_router(auth_router)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(access_admin_router, prefix="/api/v1")
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
