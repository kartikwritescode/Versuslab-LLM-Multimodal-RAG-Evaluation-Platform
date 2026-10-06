import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/metrics is public and returns prometheus text format
        resp = await client.get("/api/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")

        content = resp.text
        assert "versuslab_races_total" in content
        assert "versuslab_model_requests_total" in content
        assert "versuslab_model_ttft_seconds" in content
        assert "versuslab_model_latency_seconds" in content


@pytest.mark.asyncio
async def test_correlation_id_middleware() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Without x-request-id in request: automatically generated and returned
        resp1 = await client.get("/api/health")
        assert resp1.status_code == 200
        req_id1 = resp1.headers.get("x-request-id")
        assert req_id1 is not None
        assert len(req_id1) > 0

        # 2. With client-supplied x-request-id: preserved and returned
        custom_id = "test-custom-req-id-12345"
        resp2 = await client.get("/api/health", headers={"x-request-id": custom_id})
        assert resp2.status_code == 200
        assert resp2.headers.get("x-request-id") == custom_id
