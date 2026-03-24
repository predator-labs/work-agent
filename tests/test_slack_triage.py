import pytest
from unittest.mock import AsyncMock
from capabilities.slack_triage import SlackTriage
from shared.state import StateManager
from shared.notifications import Notifier


@pytest.fixture
def state_manager(tmp_path):
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def notifier():
    n = Notifier(ntfy_topic="test", slack_user_id="U123")
    n.push = AsyncMock()
    return n


@pytest.fixture
def triage(state_manager, notifier, tmp_path):
    return SlackTriage(
        state=state_manager,
        notifier=notifier,
        skills_path=str(tmp_path / "skills"),
        repos_path=str(tmp_path / "repos"),
        slack_user_id="U123",
        jira_email="test@docyt.com",
    )


def test_slack_triage_init(triage):
    assert triage.slack_user_id == "U123"


def test_build_mcp_servers(triage):
    servers = triage.build_mcp_servers()
    assert "agent-tools" in servers
