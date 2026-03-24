import asyncio
from unittest.mock import patch, MagicMock
from shared.background import BackgroundTaskRunner
from shared.caffeinate import CaffeinateGuard

def test_caffeinate_guard_init():
    guard = CaffeinateGuard()
    assert guard._process is None
    assert guard._active_tasks == 0

def test_caffeinate_acquire_release():
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        guard = CaffeinateGuard()
        guard.acquire()
        assert guard._active_tasks == 1
        mock_popen.assert_called_once()
        guard.acquire()
        assert guard._active_tasks == 2
        assert mock_popen.call_count == 1
        guard.release()
        assert guard._active_tasks == 1
        mock_proc.terminate.assert_not_called()
        guard.release()
        assert guard._active_tasks == 0
        mock_proc.terminate.assert_called_once()

def test_caffeinate_context_manager():
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        guard = CaffeinateGuard()
        with guard:
            assert guard._active_tasks == 1
        assert guard._active_tasks == 0
        mock_proc.terminate.assert_called_once()

async def test_submit_task():
    runner = BackgroundTaskRunner()
    async def dummy_task():
        return {"result": "done"}
    task_id = await runner.submit("test-task", dummy_task())
    assert task_id == "test-task"
    await asyncio.sleep(0.1)
    status = runner.get_status("test-task")
    assert status.state == "completed"
    assert status.result == {"result": "done"}

async def test_submit_failing_task():
    runner = BackgroundTaskRunner()
    async def failing_task():
        raise ValueError("something broke")
    await runner.submit("fail-task", failing_task())
    await asyncio.sleep(0.1)
    status = runner.get_status("fail-task")
    assert status.state == "failed"
    assert "something broke" in status.error

async def test_list_active_tasks():
    runner = BackgroundTaskRunner()
    event = asyncio.Event()
    async def long_task():
        await event.wait()
        return {"done": True}
    await runner.submit("long-1", long_task())
    await asyncio.sleep(0.05)
    active = runner.list_active()
    assert len(active) == 1
    assert active[0].task_id == "long-1"
    assert active[0].state == "running"
    event.set()
    await asyncio.sleep(0.1)
    active = runner.list_active()
    assert len(active) == 0

async def test_get_all_statuses():
    runner = BackgroundTaskRunner()
    async def quick():
        return "ok"
    await runner.submit("t1", quick())
    await runner.submit("t2", quick())
    await asyncio.sleep(0.1)
    all_statuses = runner.get_all_statuses()
    assert len(all_statuses) == 2
