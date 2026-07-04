from fastapi.testclient import TestClient

from newsintel.main import create_app


def test_liveness_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "news-intelligence-api",
    }


def test_openapi_exposes_synchronized_acquisition_endpoints() -> None:
    schema = create_app().openapi()

    assert "/api/v1/admin/publishers" in schema["paths"]
    assert "/api/v1/admin/discovery-channels" in schema["paths"]
    assert "/api/v1/admin/discovery-channels/{channel_id}/poll" in schema["paths"]
    assert "/api/v1/internal/discoveries" in schema["paths"]
    assert "/api/v1/articles" in schema["paths"]
    assert "/api/v1/articles/{article_id}" in schema["paths"]
    assert "/api/v1/articles/{article_id}/claims" in schema["paths"]
    assert "/api/v1/events/{event_id}" in schema["paths"]
    assert "/api/v1/publishers" in schema["paths"]
    assert "/api/v1/publishers/discover" in schema["paths"]
    assert "/api/v1/publishers/{publisher_id}/fetch" in schema["paths"]
    assert "/api/v1/fetch/all" in schema["paths"]
    assert "/api/v1/fetch-jobs/{job_id}" in schema["paths"]
    assert "/news-sources" in schema["paths"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
