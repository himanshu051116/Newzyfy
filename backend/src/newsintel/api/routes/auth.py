from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from newsintel.api.dependencies import AuthenticatedUserDependency, AuthServiceDependency
from newsintel.application.auth.dto import IdentityClaims, PlatformUserView
from newsintel.application.auth.service import AccessDeniedError
from newsintel.core.config import Settings
from newsintel.core.ids import uuid7
from newsintel.core.jwt import (
    JwtValidationError,
    decode_hs256_jwt,
    decode_oidc_jwt,
    encode_hs256_jwt,
)
from newsintel.domain.access import AccessStatus

router = APIRouter(tags=["auth"])


class AuthStatusResponse(BaseModel):
    user: PlatformUserView
    permissions: frozenset[str]


@router.get("/auth/login")
async def login(request: Request) -> Response:
    settings = request.app.state.settings
    if settings.auth_mode != "oidc":
        if settings.dev_auth_bypass_enabled and settings.environment != "production":
            return RedirectResponse(url="/app", status_code=status.HTTP_302_FOUND)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_not_configured",
                "message": "sign in is not configured for this deployment",
            },
        )
    if not settings.auth_oidc_authorization_url or not settings.auth_oidc_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_not_configured",
                "message": "sign in is not configured for this deployment",
            },
        )
    state = uuid7().hex
    nonce = uuid7().hex
    redirect_uri = settings.auth_oidc_redirect_uri or f"{settings.public_base_url}/auth/callback"
    state_token = _state_token(
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
        settings=settings,
    )
    params = {
        "response_type": "code",
        "client_id": settings.auth_oidc_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    response = RedirectResponse(
        url=f"{settings.auth_oidc_authorization_url}?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        "newsintel_auth_state",
        state_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=600,
    )
    return response


@router.get("/auth/callback")
async def callback(
    request: Request,
    service: AuthServiceDependency,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    settings = request.app.state.settings
    if error:
        return RedirectResponse(url="/sign-in?error=provider", status_code=status.HTTP_302_FOUND)
    if not code or not state:
        return RedirectResponse(
            url="/sign-in?error=missing-code",
            status_code=status.HTTP_302_FOUND,
        )
    try:
        state_claims = _decode_state_token(
            request.cookies.get("newsintel_auth_state"),
            settings=settings,
        )
    except JwtValidationError:
        return RedirectResponse(url="/sign-in?error=state", status_code=status.HTTP_302_FOUND)
    if state_claims.get("state") != state:
        return RedirectResponse(url="/sign-in?error=state", status_code=status.HTTP_302_FOUND)
    token_payload = await _exchange_code(
        request,
        code=code,
        redirect_uri=str(state_claims["redirect_uri"]),
    )
    id_token = token_payload.get("id_token")
    if not isinstance(id_token, str):
        return RedirectResponse(url="/sign-in?error=no-token", status_code=status.HTTP_302_FOUND)
    try:
        claims = _decode_id_token(id_token, settings)
        if claims.get("nonce") != state_claims.get("nonce"):
            raise JwtValidationError("nonce mismatch")
        user = await service.authenticate_identity(
            _identity_from_claims(claims, provider=settings.auth_provider_name),
            credential_source="oidc_callback",
            request_metadata={"path": "/auth/callback"},
            bootstrap_owner_provider=settings.bootstrap_owner_provider,
            bootstrap_owner_user_id=settings.bootstrap_owner_user_id,
            bootstrap_owner_email=settings.bootstrap_owner_email,
        )
    except (AccessDeniedError, JwtValidationError, RuntimeError):
        return RedirectResponse(url="/sign-in?error=identity", status_code=status.HTTP_302_FOUND)
    target = _target_for_status(user.access_status)
    session_token = _session_token(
        provider=user.auth_provider,
        provider_user_id=user.auth_provider_user_id,
        verified_email=user.verified_email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        settings=settings,
    )
    csrf_token = uuid7().hex
    response = RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    response.delete_cookie("newsintel_auth_state")
    response.set_cookie(
        settings.auth_cookie_name,
        session_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.auth_session_ttl_seconds,
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.auth_session_ttl_seconds,
    )
    return response


@router.post("/auth/logout")
@router.get("/auth/logout")
async def logout(request: Request) -> Response:
    settings = request.app.state.settings
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.auth_cookie_name)
    response.delete_cookie(settings.auth_csrf_cookie_name)
    response.delete_cookie("newsintel_auth_state")
    return response


@router.get("/api/v1/auth/me", response_model=AuthStatusResponse)
async def me(user: AuthenticatedUserDependency) -> AuthStatusResponse:
    return AuthStatusResponse(
        user=PlatformUserView(**user.model_dump(exclude={"permissions", "credential_source"})),
        permissions=user.permissions,
    )


def _target_for_status(status_value: AccessStatus) -> str:
    if status_value == AccessStatus.APPROVED:
        return "/app"
    if status_value == AccessStatus.PENDING:
        return "/pending"
    return "/access-denied"


def _state_token(
    *,
    state: str,
    nonce: str,
    redirect_uri: str,
    settings: Settings,
) -> str:
    now = datetime.now(UTC)
    secret = settings.auth_session_secret.get_secret_value()
    return encode_hs256_jwt(
        {
            "iss": "newsintel-auth-state",
            "aud": "newsintel-api",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
            "state": state,
            "nonce": nonce,
            "redirect_uri": redirect_uri,
        },
        secret=secret,
    )


def _decode_state_token(token: str | None, *, settings: Settings) -> dict[str, object]:
    if not token:
        raise JwtValidationError("missing state")
    secret = settings.auth_session_secret.get_secret_value()
    return decode_hs256_jwt(
        token,
        secret=secret,
        issuer="newsintel-auth-state",
        audience="newsintel-api",
    )


def _session_token(
    *,
    provider: str,
    provider_user_id: str,
    verified_email: str | None,
    display_name: str | None,
    avatar_url: str | None,
    settings: Settings,
) -> str:
    now = datetime.now(UTC)
    secret = settings.auth_session_secret.get_secret_value()
    return encode_hs256_jwt(
        {
            "iss": "newsintel-session",
            "aud": "newsintel-api",
            "iat": int(now.timestamp()),
            "exp": int(now.timestamp() + settings.auth_session_ttl_seconds),
            "sub": provider_user_id,
            "provider": provider,
            "email": verified_email,
            "email_verified": True,
            "name": display_name,
            "picture": avatar_url,
        },
        secret=secret,
    )


async def _exchange_code(
    request: Request,
    *,
    code: str,
    redirect_uri: str,
) -> dict[str, object]:
    settings = request.app.state.settings
    if not settings.auth_oidc_token_url or not settings.auth_oidc_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            settings.auth_oidc_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.auth_oidc_client_id,
                "client_secret": settings.auth_oidc_client_secret.get_secret_value(),
            },
            headers={"Accept": "application/json"},
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY)
    return payload


def _decode_id_token(token: str, settings: Settings) -> dict[str, object]:
    issuer = settings.auth_jwt_issuer
    audience = settings.auth_jwt_audience
    algorithms = settings.auth_algorithm_list
    if not issuer or not audience:
        raise JwtValidationError("JWT issuer and audience are not configured")
    if algorithms == ["HS256"]:
        secret = settings.auth_jwt_hs256_secret.get_secret_value()
        return decode_hs256_jwt(token, secret=secret, issuer=issuer, audience=audience)
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


def _identity_from_claims(claims: dict[str, object], *, provider: str) -> IdentityClaims:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise JwtValidationError("missing subject")
    email = claims.get("email")
    name = claims.get("name") or claims.get("preferred_username")
    picture = claims.get("picture") or claims.get("avatar_url")
    return IdentityClaims(
        provider=provider,
        provider_user_id=subject,
        verified_email=email if isinstance(email, str) else None,
        email_verified=bool(claims.get("email_verified")),
        display_name=name if isinstance(name, str) else None,
        avatar_url=picture if isinstance(picture, str) else None,
    )
