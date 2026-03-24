"""
Integration smoke tests — verify all components wire together.
These don't call real APIs; they test initialization and routing.
"""
import os
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def env_vars():
    return {
        "ANTHROPIC_API_KEY": "test-key",
        "AGENT_SECRET": "test-secret",
        "SLACK_USER_ID": "U123",
        "JIRA_EMAIL": "test@docyt.com",
        "OBSIDIAN_VAULT_PATH": "/tmp/vault",
        "REPOS_PATH": "/tmp/repos",
        "SKILLS_PATH": "/tmp/skills",
    }


async def test_server_starts_and_health(env_vars):
    with patch.dict(os.environ, env_vars):
        from server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


async def test_status_returns_empty_pending(env_vars):
    with patch.dict(os.environ, env_vars):
        from server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/status",
                headers={"Authorization": "Bearer test-secret"},
            )
            assert resp.status_code == 200
            assert resp.json()["pending_approvals"] == []


async def test_approve_nonexistent_returns_error(env_vars):
    with patch.dict(os.environ, env_vars):
        from server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/approve/nonexistent",
                headers={"Authorization": "Bearer test-secret"},
            )
            assert resp.status_code == 404
