import pytest
from unittest.mock import AsyncMock
from capabilities.pr_reviewer import PRReviewer
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
def reviewer(state_manager, notifier, tmp_path):
    return PRReviewer(
        state=state_manager,
        notifier=notifier,
        skills_path=str(tmp_path / "skills"),
        repos_path=str(tmp_path / "repos"),
        memory_path=str(tmp_path / "memory"),
    )


def test_pr_reviewer_init(reviewer):
    assert reviewer is not None


def test_parse_pr_url(reviewer):
    repo, pr_num = reviewer.parse_pr_url(
        "https://bitbucket.org/kmnss/docyt-mlai/pull-requests/123"
    )
    assert repo == "docyt-mlai"
    assert pr_num == "123"


def test_parse_pr_url_with_uuid(reviewer):
    repo, pr_num = reviewer.parse_pr_url(
        "https://bitbucket.org/kmnss/docyt-server/pull-requests/456/diff"
    )
    assert repo == "docyt-server"
    assert pr_num == "456"


def test_parse_pr_url_invalid(reviewer):
    with pytest.raises(ValueError):
        reviewer.parse_pr_url("https://github.com/some/repo")
