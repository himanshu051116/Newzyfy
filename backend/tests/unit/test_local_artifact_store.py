from datetime import UTC, datetime

import pytest

from newsintel.adapters.artifacts.local_store import LocalRawArtifactStore
from newsintel.core.ids import uuid7


@pytest.mark.asyncio
async def test_local_raw_artifact_store_writes_html_snapshot(tmp_path) -> None:
    store = LocalRawArtifactStore(tmp_path)
    body = b"<html><body><p>Article body</p></body></html>"
    body_sha256 = "a" * 64

    artifact = await store.save_raw_html(
        candidate_id=uuid7(),
        body=body,
        body_sha256=body_sha256,
        retrieved_at=datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
    )

    assert artifact.storage_backend == "local_filesystem"
    assert artifact.sha256 == body_sha256
    assert artifact.byte_size == len(body)
    assert artifact.artifact_uri.endswith(f"{body_sha256}.html")
