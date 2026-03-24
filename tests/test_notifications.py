import pytest
from shared.notifications import Notifier


@pytest.fixture
def notifier():
    return Notifier(ntfy_topic="test-topic", slack_user_id="U123")


async def test_ntfy_push(notifier, httpx_mock):
    httpx_mock.add_response(url="https://ntfy.sh/test-topic", status_code=200)
    await notifier.push("Test notification", title="Test", priority="high")
    request = httpx_mock.get_request()
    assert request.url == "https://ntfy.sh/test-topic"
    assert request.headers["Title"] == "Test"
    assert request.headers["Priority"] == "high"
    assert request.content == b"Test notification"


async def test_ntfy_push_default_priority(notifier, httpx_mock):
    httpx_mock.add_response(url="https://ntfy.sh/test-topic", status_code=200)
    await notifier.push("Test")
    request = httpx_mock.get_request()
    assert request.headers["Priority"] == "default"


async def test_format_approval_message(notifier):
    msg = notifier.format_approval_message(
        task_id="abc-123",
        action="Send Slack reply",
        details="Draft: 'The ML pipeline is running fine.'",
    )
    assert "abc-123" in msg
    assert "Send Slack reply" in msg
    assert "Draft:" in msg
    assert "/approve/abc-123" in msg
