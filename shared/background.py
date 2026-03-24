import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Coroutine

from shared.caffeinate import CaffeinateGuard


@dataclass
class TaskStatus:
    task_id: str
    state: str
    started_at: str
    completed_at: str | None = None
    result: Any = None
    error: str | None = None
    description: str = ""


class BackgroundTaskRunner:
    def __init__(self):
        self._tasks: dict[str, TaskStatus] = {}
        self._async_tasks: dict[str, asyncio.Task] = {}
        self._caffeinate = CaffeinateGuard()

    async def submit(self, task_id: str, coro: Coroutine, description: str = "") -> str:
        self._caffeinate.acquire()
        status = TaskStatus(task_id=task_id, state="running", started_at=datetime.now(timezone.utc).isoformat(), description=description)
        self._tasks[task_id] = status

        async def _wrapper():
            try:
                result = await coro
                status.state = "completed"
                status.result = result
                status.completed_at = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                status.state = "failed"
                status.error = str(e)
                status.completed_at = datetime.now(timezone.utc).isoformat()
            finally:
                self._caffeinate.release()
                self._async_tasks.pop(task_id, None)

        self._async_tasks[task_id] = asyncio.create_task(_wrapper())
        return task_id

    def get_status(self, task_id: str) -> TaskStatus | None:
        return self._tasks.get(task_id)

    def list_active(self) -> list[TaskStatus]:
        return [s for s in self._tasks.values() if s.state == "running"]

    def get_all_statuses(self) -> list[TaskStatus]:
        return list(self._tasks.values())

    async def cancel(self, task_id: str) -> bool:
        task = self._async_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            self._tasks[task_id].state = "cancelled"
            self._tasks[task_id].completed_at = datetime.now(timezone.utc).isoformat()
            self._caffeinate.release()
            return True
        return False
