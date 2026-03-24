import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE = {"slack": {"last_read": {}}, "pr_reviews": {}, "pending_approvals": {}, "issues": {}}


class StateManager:
    def __init__(self, path: str | Path = "data/state.json"):
        self._path = Path(path)
        self._lock = asyncio.Lock()

    async def read(self) -> dict:
        async with self._lock:
            return self._read_sync()

    def _read_sync(self) -> dict:
        if not self._path.exists():
            return json.loads(json.dumps(DEFAULT_STATE))
        with open(self._path) as f:
            return json.load(f)

    async def write(self, data: dict) -> None:
        async with self._lock:
            self._write_sync(data)

    def _write_sync(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(self._path)

    async def update(self, key_path: str, value: Any) -> None:
        async with self._lock:
            data = self._read_sync()
            keys = key_path.split(".")
            obj = data
            for k in keys[:-1]:
                obj = obj.setdefault(k, {})
            obj[keys[-1]] = value
            self._write_sync(data)

    async def add_pending_approval(self, task_id: str, approval_type: str, payload: dict, context: dict) -> dict:
        approval = {"task_id": task_id, "type": approval_type, "status": "pending_approval", "created_at": datetime.now(timezone.utc).isoformat(), "payload": payload, "context": context}
        async with self._lock:
            data = self._read_sync()
            data.setdefault("pending_approvals", {})[task_id] = approval
            self._write_sync(data)
        return approval

    async def approve(self, task_id: str) -> dict:
        async with self._lock:
            data = self._read_sync()
            if task_id not in data.get("pending_approvals", {}):
                raise KeyError(f"No pending approval with id: {task_id}")
            data["pending_approvals"][task_id]["status"] = "approved"
            self._write_sync(data)
            return data["pending_approvals"][task_id]

    async def reject(self, task_id: str) -> dict:
        async with self._lock:
            data = self._read_sync()
            if task_id not in data.get("pending_approvals", {}):
                raise KeyError(f"No pending approval with id: {task_id}")
            data["pending_approvals"][task_id]["status"] = "rejected"
            self._write_sync(data)
            return data["pending_approvals"][task_id]

    async def get_pending_approvals(self) -> list[dict]:
        state = await self.read()
        return [{**v, "task_id": k} for k, v in state.get("pending_approvals", {}).items() if v.get("status") == "pending_approval"]

    async def save_pr_review(self, pr_id: str, decision: str, issues: list[dict]) -> None:
        review = {"reviewed_at": datetime.now(timezone.utc).isoformat(), "decision": decision, "issues_raised": [{**issue, "resolved": False} for issue in issues]}
        async with self._lock:
            data = self._read_sync()
            data.setdefault("pr_reviews", {})[pr_id] = review
            self._write_sync(data)

    async def get_pr_review(self, pr_id: str) -> dict | None:
        state = await self.read()
        return state.get("pr_reviews", {}).get(pr_id)

    async def save_issue(self, issue_id: str, issue_data: dict) -> None:
        await self.update(f"issues.{issue_id}", issue_data)

    async def get_issue(self, issue_id: str) -> dict | None:
        state = await self.read()
        return state.get("issues", {}).get(issue_id)
