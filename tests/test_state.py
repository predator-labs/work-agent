import asyncio
import json
import pytest
from pathlib import Path
from shared.state import StateManager


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture
def state_manager(state_file):
    return StateManager(state_file)


async def test_read_empty_state(state_manager):
    state = await state_manager.read()
    assert state == {"slack": {"last_read": {}}, "pr_reviews": {}, "pending_approvals": {}, "issues": {}}


async def test_write_and_read(state_manager):
    await state_manager.update("slack.last_read.C123", "1234567890.123")
    state = await state_manager.read()
    assert state["slack"]["last_read"]["C123"] == "1234567890.123"


async def test_add_pending_approval(state_manager):
    await state_manager.add_pending_approval(task_id="test-uuid", approval_type="slack_reply", payload={"message": "hello", "channel": "C123"}, context={"slack_thread_ts": "123.456"})
    state = await state_manager.read()
    approval = state["pending_approvals"]["test-uuid"]
    assert approval["type"] == "slack_reply"
    assert approval["status"] == "pending_approval"
    assert approval["payload"]["message"] == "hello"


async def test_approve_pending(state_manager):
    await state_manager.add_pending_approval(task_id="test-uuid", approval_type="slack_reply", payload={"message": "hello"}, context={})
    approval = await state_manager.approve("test-uuid")
    assert approval["status"] == "approved"
    state = await state_manager.read()
    assert state["pending_approvals"]["test-uuid"]["status"] == "approved"


async def test_reject_pending(state_manager):
    await state_manager.add_pending_approval(task_id="test-uuid", approval_type="slack_reply", payload={"message": "hello"}, context={})
    await state_manager.reject("test-uuid")
    state = await state_manager.read()
    assert state["pending_approvals"]["test-uuid"]["status"] == "rejected"


async def test_approve_nonexistent_raises(state_manager):
    with pytest.raises(KeyError):
        await state_manager.approve("nonexistent")


async def test_concurrent_writes_no_corruption(state_manager):
    async def write_channel(i):
        await state_manager.update(f"slack.last_read.C{i}", f"ts-{i}")
    await asyncio.gather(*[write_channel(i) for i in range(20)])
    state = await state_manager.read()
    assert len(state["slack"]["last_read"]) == 20


async def test_get_pending_approvals(state_manager):
    await state_manager.add_pending_approval("t1", "slack_reply", {}, {})
    await state_manager.add_pending_approval("t2", "jira_ticket", {}, {})
    await state_manager.approve("t1")
    pending = await state_manager.get_pending_approvals()
    assert len(pending) == 1
    assert pending[0]["task_id"] == "t2"


async def test_save_pr_review(state_manager):
    await state_manager.save_pr_review(pr_id="my-repo/123", decision="changes_requested", issues=[{"file": "app.py", "line": 42, "severity": "critical", "description": "SQL injection"}])
    state = await state_manager.read()
    review = state["pr_reviews"]["my-repo/123"]
    assert review["decision"] == "changes_requested"
    assert len(review["issues_raised"]) == 1
