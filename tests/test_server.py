# tests/test_server.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


ENV_VARS = {
    "ANTHROPIC_API_KEY": "test",
    "AGENT_SECRET": "test-secret",
}


@pytest.fixture
def app():
    # Patch settings to avoid needing real env vars
    with patch.dict("os.environ", ENV_VARS):
        from server import app
        return app


async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


async def test_auth_required(app):
    with patch.dict("os.environ", ENV_VARS):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/run/slack")
            assert response.status_code == 401


async def test_auth_with_secret(app):
    with patch.dict("os.environ", ENV_VARS):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("server.slack_triage") as mock_triage:
                mock_triage.run = AsyncMock(return_value={"status": "ok"})
                response = await client.post(
                    "/run/slack",
                    headers={"Authorization": "Bearer test-secret"},
                )
                assert response.status_code == 200


async def test_status_endpoint(app):
    with patch.dict("os.environ", ENV_VARS):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/status",
                headers={"Authorization": "Bearer test-secret"},
            )
            assert response.status_code == 200
