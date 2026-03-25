import pytest
from unittest.mock import AsyncMock
from capabilities.issue_handler import IssueHandler
from shared.state import StateManager
from shared.notifications import Notifier
from shared.custom_tools import reset_server_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_server_cache()
    yield
    reset_server_cache()


@pytest.fixture
def state_manager(tmp_path):
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def notifier():
    n = Notifier(ntfy_topic="test", slack_user_id="U123")
    n.push = AsyncMock()
    return n


@pytest.fixture
def handler(state_manager, notifier, tmp_path):
    return IssueHandler(
        state=state_manager,
        notifier=notifier,
        skills_path=str(tmp_path / "skills"),
        repos_path=str(tmp_path / "repos"),
        memory_path=str(tmp_path / "memory"),
        jira_email="test@docyt.com",
    )


def test_issue_handler_init(handler):
    assert handler.jira_email == "test@docyt.com"


async def test_create_issue_entry(handler):
    issue_id = await handler.create_issue("Fix login bug", {"channel": "C123"})
    assert issue_id is not None
    issue = await handler.state.get_issue(issue_id)
    assert issue["status"] == "investigating"
    assert issue["description"] == "Fix login bug"
