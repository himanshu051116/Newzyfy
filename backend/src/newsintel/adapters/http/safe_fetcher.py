import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urljoin, urlsplit

import httpx


class UnsafeTargetError(ValueError):
    """Raised when a target resolves to a disallowed network address."""


@dataclass(frozen=True, slots=True)
class FetchRequest:
    url: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    body_sha256: str
    retrieved_at: datetime
    redirect_chain: tuple[str, ...]

    @property
    def not_modified(self) -> bool:
        return self.status_code == 304


async def _assert_public_hostname(hostname: str) -> None:
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM),
    )
    if not results:
        raise UnsafeTargetError("hostname did not resolve")
    for result in results:
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise UnsafeTargetError(f"target resolves to non-public address: {address}")


async def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeTargetError("only public HTTP and HTTPS URLs are allowed")
    await _assert_public_hostname(parsed.hostname)


class SafeHttpFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 20,
        max_bytes: int = 8_000_000,
        max_redirects: int = 5,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    async def fetch(self, request: FetchRequest) -> FetchResult:
        current = request.url
        redirects: list[str] = []
        headers = {"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"}
        if request.etag:
            headers["If-None-Match"] = request.etag
        if request.last_modified:
            headers["If-Modified-Since"] = request.last_modified

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
        ) as client:
            for _ in range(self._max_redirects + 1):
                await _validate_url(current)
                async with client.stream("GET", current, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise httpx.HTTPError("redirect response omitted Location")
                        redirects.append(current)
                        current = urljoin(current, location)
                        continue

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise httpx.HTTPError("response exceeded configured byte limit")
                    body_bytes = bytes(body)
                    return FetchResult(
                        requested_url=request.url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=body_bytes,
                        body_sha256=sha256(body_bytes).hexdigest(),
                        retrieved_at=datetime.now(UTC),
                        redirect_chain=tuple(redirects),
                    )
        raise httpx.TooManyRedirects("redirect limit exceeded", request=None)

