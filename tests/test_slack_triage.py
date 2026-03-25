import json
import pytest
from unittest.mock import AsyncMock
from capabilities.slack_triage import SlackTriage, _parse_triage_result
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


def test_parse_triage_result_valid_json():
    raw = json.dumps({
        "simple": [{"channel": "C1", "summary": "greeting"}],
        "pr_reviews": [{"url": "https://bb.org/pr/1", "requester": "user1"}],
        "issues": [],
        "informational": [{"channel": "C2", "summary": "announcement"}],
    })
    result = _parse_triage_result(raw)
    assert result is not None
    assert len(result["simple"]) == 1
    assert len(result["pr_reviews"]) == 1
    assert len(result["issues"]) == 0
    assert len(result["informational"]) == 1


def test_parse_triage_result_json_in_code_block():
    raw = '```json\n{"simple": [], "pr_reviews": [], "issues": [{"description": "bug"}], "informational": []}\n```'
    result = _parse_triage_result(raw)
    assert result is not None
    assert len(result["issues"]) == 1


def test_parse_triage_result_invalid():
    result = _parse_triage_result("not json at all")
    assert result is None


def test_parse_triage_result_empty():
    result = _parse_triage_result("")
    assert result is None


def test_parse_triage_result_partial_keys():
    raw = json.dumps({"simple": [{"channel": "C1"}], "pr_reviews": []})
    result = _parse_triage_result(raw)
    assert result is not None
    assert len(result["simple"]) == 1
    assert result["issues"] == []
    assert result["informational"] == []
