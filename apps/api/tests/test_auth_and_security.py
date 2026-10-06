import datetime

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter
from app.main import app


# ---------------------------------------------------------------------------
# 1. Password Hashing Tests (Argon2id via pwdlib)
# ---------------------------------------------------------------------------
def test_password_hashing_and_verification():
    secret = "SuperSecretPassword123!"
    hashed = hash_password(secret)

    # Must be valid Argon2id hash
    assert hashed.startswith("$argon2id$")
    assert verify_password(secret, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_creation_and_validation():
    token = create_access_token("admin", expires_delta=datetime.timedelta(minutes=5))
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert "exp" in payload

    # Test expired token
    expired_token = create_access_token("admin", expires_delta=datetime.timedelta(seconds=-10))
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(expired_token)


# ---------------------------------------------------------------------------
# 2. Direct Access Verification (No Auth Required)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_endpoints_work_directly_without_auth():
    """Verifies that API endpoints can be accessed directly without authentication headers."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.db.base import get_session

    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_session.scalars.return_value = mock_scalars

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        with patch("app.api.race.list_races", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = ([], 0)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. GET /api/races works directly without token
                resp = await client.get("/api/races")
                assert resp.status_code == 200

                # 2. GET /api/documents works directly without token
                resp = await client.get("/api/documents")
                assert resp.status_code == 200

                # 3. Public health endpoint works directly
                health_resp = await client.get("/api/health")
                assert health_resp.status_code == 200
                assert health_resp.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# 4. In-Memory Rate Limiting Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limiter_exceeded():
    limiter = InMemoryRateLimiter(requests_per_minute=2, window_seconds=60.0)

    class FakeRequest:
        class FakeClient:
            host = "192.168.1.100"
        client = FakeClient()

    req = FakeRequest()

    # Call 1: ok
    await limiter(req)
    # Call 2: ok
    await limiter(req)

    # Call 3: exceeded -> raises 429 with Retry-After header
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await limiter(req)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


# ---------------------------------------------------------------------------
# 5. Request Size & MIME Validation on Document Upload
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upload_request_size_and_mime_validation(monkeypatch: pytest.MonkeyPatch):
    # Set max upload size to 100 bytes for test
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Oversized file -> 413
        oversized_content = b"A" * 200
        resp = await client.post(
            "/api/documents",
            files={"file": ("large.txt", oversized_content, "text/plain")},
        )
        assert resp.status_code == 413
        assert "exceeds maximum allowed size" in resp.json()["detail"]

        # 2. Binary file with null bytes disguised as .txt -> 400
        binary_content = b"Hello\x00World\x00Binary"
        resp = await client.post(
            "/api/documents",
            files={"file": ("fake.txt", binary_content, "text/plain")},
        )
        assert resp.status_code == 400
        assert "Binary file detected" in resp.json()["detail"]

        # 3. Invalid MIME type -> 400
        resp = await client.post(
            "/api/documents",
            files={"file": ("doc.txt", b"Valid content", "image/png")},
        )
        assert resp.status_code == 400
        assert "Unsupported MIME type" in resp.json()["detail"]
