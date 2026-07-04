import base64
import hashlib
import hmac
import importlib
import json
import time
from collections.abc import Mapping
from typing import Any


class JwtValidationError(ValueError):
    pass


def encode_hs256_jwt(payload: dict[str, object], *, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_json(header)
    payload_b64 = _b64url_json(payload)
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_hs256_jwt(
    token: str,
    *,
    secret: str,
    issuer: str | None = None,
    audience: str | None = None,
    leeway_seconds: int = 30,
) -> dict[str, Any]:
    header, payload, signing_input, supplied_signature = _split_token(token)
    if header.get("alg") != "HS256":
        raise JwtValidationError("unsupported token algorithm")
    expected = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, supplied_signature):
        raise JwtValidationError("invalid token signature")
    _validate_claims(payload, issuer=issuer, audience=audience, leeway_seconds=leeway_seconds)
    return payload


def decode_oidc_jwt(
    token: str,
    *,
    issuer: str,
    audience: str,
    algorithms: list[str],
    jwks_url: str,
) -> dict[str, Any]:
    jwt_module = importlib.import_module("jwt")
    jwk_client = jwt_module.PyJWKClient(jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    return dict(
        jwt_module.decode(
            token,
            signing_key.key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    )


def unverified_claims(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        return _b64url_json_decode(parts[1])
    except Exception:
        return {}


def _validate_claims(
    payload: dict[str, Any],
    *,
    issuer: str | None,
    audience: str | None,
    leeway_seconds: int,
) -> None:
    now = int(time.time())
    exp = payload.get("exp")
    if not isinstance(exp, int | float) or exp + leeway_seconds < now:
        raise JwtValidationError("token has expired")
    nbf = payload.get("nbf")
    if isinstance(nbf, int | float) and nbf - leeway_seconds > now:
        raise JwtValidationError("token is not active")
    if issuer is not None and payload.get("iss") != issuer:
        raise JwtValidationError("invalid token issuer")
    if audience is not None:
        aud = payload.get("aud")
        valid = aud == audience or (isinstance(aud, list) and audience in aud)
        if not valid:
            raise JwtValidationError("invalid token audience")


def _split_token(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise JwtValidationError("malformed token")
    header = _b64url_json_decode(parts[0])
    payload = _b64url_json_decode(parts[1])
    signature = _b64url_decode(parts[2])
    return header, payload, f"{parts[0]}.{parts[1]}".encode("ascii"), signature


def _b64url_json(value: Mapping[str, object]) -> str:
    return _b64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64url_json_decode(value: str) -> dict[str, Any]:
    decoded = json.loads(_b64url_decode(value))
    if not isinstance(decoded, dict):
        raise JwtValidationError("expected JSON object")
    return decoded


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
