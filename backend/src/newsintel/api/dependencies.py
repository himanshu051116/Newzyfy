import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from newsintel.adapters.http.safe_fetcher import SafeHttpFetcher
from newsintel.application.acquisition.polling import PollingRepository
from newsintel.application.acquisition.service import AcquisitionService
from newsintel.application.articles.query_service import ArticleQueryService
from newsintel.application.sources.service import SourceService
from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository
from newsintel.infrastructure.db.unit_of_work import SqlAlchemyAcquisitionUnitOfWork

internal_token_header = APIKeyHeader(
    name="X-Internal-Token",
    scheme_name="InternalServiceToken",
    auto_error=False,
)


async def require_internal_token(
    request: Request,
    supplied_token: Annotated[str | None, Security(internal_token_header)],
) -> None:
    expected = request.app.state.settings.internal_api_token.get_secret_value()
    if not supplied_token or not secrets.compare_digest(supplied_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal service token",
        )


def get_acquisition_service(request: Request) -> AcquisitionService:
    session_factory = request.app.state.database.session_factory
    return AcquisitionService(
        lambda: SqlAlchemyAcquisitionUnitOfWork(session_factory)
    )


def get_polling_repository(request: Request) -> PollingRepository:
    return SqlAlchemyPollingRepository(request.app.state.database.session_factory)


def get_article_query_service(request: Request) -> ArticleQueryService:
    return ArticleQueryService(request.app.state.database.session_factory)


def get_source_service(request: Request) -> SourceService:
    settings = request.app.state.settings
    fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    return SourceService(
        session_factory=request.app.state.database.session_factory,
        fetcher=fetcher,
    )


InternalAuth = Annotated[None, Depends(require_internal_token)]
AcquisitionServiceDependency = Annotated[
    AcquisitionService,
    Depends(get_acquisition_service),
]
PollingRepositoryDependency = Annotated[
    PollingRepository,
    Depends(get_polling_repository),
]
ArticleQueryServiceDependency = Annotated[
    ArticleQueryService,
    Depends(get_article_query_service),
]
SourceServiceDependency = Annotated[
    SourceService,
    Depends(get_source_service),
]
