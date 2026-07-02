import pytest

from newsintel.adapters.http.safe_fetcher import UnsafeTargetError, _validate_url


@pytest.mark.asyncio
async def test_rejects_localhost_to_prevent_ssrf() -> None:
    with pytest.raises(UnsafeTargetError, match="non-public"):
        await _validate_url("http://127.0.0.1/private")


@pytest.mark.asyncio
async def test_rejects_non_http_scheme() -> None:
    with pytest.raises(UnsafeTargetError, match="only public HTTP"):
        await _validate_url("file:///etc/passwd")

