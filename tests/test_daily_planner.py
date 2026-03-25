import pytest
from unittest.mock import AsyncMock
from capabilities.daily_planner import DailyPlanner
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
def planner(state_manager, notifier, tmp_path):
    vault = tmp_path / "vault" / "daily-logs"
    vault.mkdir(parents=True)
    return DailyPlanner(
        state=state_manager,
        notifier=notifier,
        skills_path=str(tmp_path / "skills"),
        repos_path=str(tmp_path / "repos"),
        vault_path=str(tmp_path / "vault"),
        jira_email="test@docyt.com",
    )


def test_daily_planner_init(planner):
    assert planner.jira_email == "test@docyt.com"


def test_today_log_path(planner):
    path = planner.today_log_path()
    assert "daily-logs" in str(path)
    assert ".md" in str(path)
