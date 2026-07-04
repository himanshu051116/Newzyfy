from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from newsintel.adapters.http.safe_fetcher import SafeHttpFetcher
from newsintel.application.acquisition.polling import PollingRepository
from newsintel.application.acquisition.service import AcquisitionService
from newsintel.application.articles.query_service import ArticleQueryService
from newsintel.application.auth.dto import CurrentUser, IdentityClaims
from newsintel.application.auth.service import (
    AccessDeniedError,
    PlatformAuthService,
    assert_approved,
    assert_permission,
)
from newsintel.application.sources.service import SourceService
from newsintel.core.config import Settings
from newsintel.core.jwt import (
    JwtValidationError,
    decode_hs256_jwt,
    decode_oidc_jwt,
)
from newsintel.domain.access import Permission
from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository
from newsintel.infrastructure.db.unit_of_work import SqlAlchemyAcquisitionUnitOfWork

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(request: Request) -> PlatformAuthService:
    return PlatformAuthService(request.app.state.database.session_factory)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    service: Annotated[PlatformAuthService, Depends(get_auth_service)],
) -> CurrentUser:
    settings = request.app.state.settings
    metadata = _safe_request_metadata(request)
    try:
        if settings.dev_auth_bypass_enabled and settings.environment != "production":
            return await service.authenticate_identity(
                IdentityClaims(
                    provider=settings.dev_auth_provider,
                    provider_user_id=settings.dev_auth_user_id,
                    verified_email=settings.dev_auth_email,
                    email_verified=True,
                    display_name=settings.dev_auth_display_name,
                ),
                credential_source="development_bypass",
                request_metadata=metadata,
                bootstrap_owner_provider=settings.dev_auth_provider,
                bootstrap_owner_user_id=settings.dev_auth_user_id,
                bootstrap_owner_email=settings.dev_auth_email,
            )
        token = _token_from_request(request, credentials)
        if token is None:
            raise AccessDeniedError("missing_authentication", "authentication is required")
        if token.startswith("app:"):
            claims = _decode_app_session(token.removeprefix("app:"), settings)
            credential_source = "session_cookie"
        else:
            claims = _decode_provider_jwt(token, settings)
            credential_source = "bearer"
        provider = (
            claims.get("provider")
            if credential_source == "session_cookie"
            else settings.auth_provider_name
        )
        identity = _identity_from_claims(
            claims,
            provider=provider if isinstance(provider, str) else settings.auth_provider_name,
        )
        user = await service.authenticate_identity(
            identity,
            credential_source=credential_source,
            request_metadata=metadata,
            bootstrap_owner_provider=settings.bootstrap_owner_provider,
            bootstrap_owner_user_id=settings.bootstrap_owner_user_id,
            bootstrap_owner_email=settings.bootstrap_owner_email,
        )
        if credential_source == "session_cookie" and request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            _require_csrf(request, settings.auth_csrf_cookie_name)
        return user
    except AccessDeniedError as exc:
        raise _auth_http_error(exc) from exc
    except (JwtValidationError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_authentication",
                "message": "authentication could not be verified",
            },
        ) from exc


async def require_authenticated_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return user


async def require_approved_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    try:
        assert_approved(user)
    except AccessDeniedError as exc:
        raise _auth_http_error(exc) from exc
    return user


def _permission_dependency(
    permission: Permission,
) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def dependency(
        user: Annotated[CurrentUser, Depends(require_approved_user)],
    ) -> CurrentUser:
        try:
            assert_permission(user, permission.value)
        except AccessDeniedError as exc:
            raise _auth_http_error(exc) from exc
        return user

    return dependency


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


AuthenticatedUserDependency = Annotated[
    CurrentUser,
    Depends(require_authenticated_user),
]
ApprovedUserDependency = Annotated[
    CurrentUser,
    Depends(require_approved_user),
]
ViewerAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.CONTENT_VIEW)),
]
AnalystAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.CLAIMS_VIEW)),
]
SourceManagerAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.SOURCES_MANAGE)),
]
OperationsAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.OPERATIONS_VIEW)),
]
AccessAdminAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.USERS_MANAGE)),
]
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
AuthServiceDependency = Annotated[
    PlatformAuthService,
    Depends(get_auth_service),
]


def _token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    cookie_value = request.cookies.get(request.app.state.settings.auth_cookie_name)
    if cookie_value:
        return f"app:{cookie_value}"
    return None


def _decode_provider_jwt(token: str, settings: Settings) -> dict[str, object]:
    issuer = settings.auth_jwt_issuer
    audience = settings.auth_jwt_audience
    algorithms = settings.auth_algorithm_list
    if not issuer or not audience:
        raise JwtValidationError("JWT issuer and audience are not configured")
    if algorithms == ["HS256"]:
        secret = settings.auth_jwt_hs256_secret.get_secret_value()
        if not secret:
            raise JwtValidationError("HS256 secret is not configured")
        return decode_hs256_jwt(
            token,
            secret=secret,
            issuer=issuer,
            audience=audience,
        )
    jwks_url = settings.auth_jwt_jwks_url
    if not jwks_url:
        raise JwtValidationError("JWKS URL is not configured")
    return decode_oidc_jwt(
        token,
        issuer=issuer,
        audience=audience,
        algorithms=list(algorithms),
        jwks_url=jwks_url,
    )


def _decode_app_session(token: str, settings: Settings) -> dict[str, object]:
    secret = settings.auth_session_secret.get_secret_value()
    if len(secret) < 32:
        raise JwtValidationError("session secret is not configured")
    return decode_hs256_jwt(
        token,
        secret=secret,
        issuer="newsintel-session",
        audience="newsintel-api",
    )


def _identity_from_claims(claims: dict[str, object], *, provider: str) -> IdentityClaims:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise JwtValidationError("token subject is missing")
    email = claims.get("email")
    verified = claims.get("email_verified")
    display_name = claims.get("name") or claims.get("user_name") or claims.get("preferred_username")
    avatar_url = claims.get("picture") or claims.get("avatar_url")
    return IdentityClaims(
        provider=provider,
        provider_user_id=subject,
        verified_email=email if isinstance(email, str) else None,
        email_verified=bool(verified),
        display_name=display_name if isinstance(display_name, str) else None,
        avatar_url=avatar_url if isinstance(avatar_url, str) else None,
    )


def _require_csrf(request: Request, csrf_cookie_name: str) -> None:
    cookie_value = request.cookies.get(csrf_cookie_name)
    header_value = request.headers.get("X-CSRF-Token")
    if not cookie_value or not header_value or cookie_value != header_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "csrf_required",
                "message": "request could not be verified",
            },
        )


def _auth_http_error(exc: AccessDeniedError) -> HTTPException:
    status_code = (
        status.HTTP_401_UNAUTHORIZED
        if exc.code in {"missing_authentication", "invalid_authentication", "email_unverified"}
        else status.HTTP_403_FORBIDDEN
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _safe_request_metadata(request: Request) -> dict[str, object]:
    return {
        "path": request.url.path,
        "method": request.method,
        "client_host": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
        "x_request_id": request.headers.get("x-request-id"),
    }
