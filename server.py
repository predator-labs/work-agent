# server.py
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config.settings import Settings
from shared.state import StateManager
from shared.notifications import Notifier
from shared.background import BackgroundTaskRunner
from capabilities.slack_triage import SlackTriage
from capabilities.pr_reviewer import PRReviewer
from capabilities.issue_handler import IssueHandler
from capabilities.daily_planner import DailyPlanner


# Global instances (initialized in lifespan)
settings: Settings = None
state: StateManager = None
notifier: Notifier = None
bg_runner: BackgroundTaskRunner = None
slack_triage: SlackTriage = None
pr_reviewer: PRReviewer = None
issue_handler: IssueHandler = None
daily_planner: DailyPlanner = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global settings, state, notifier, bg_runner, slack_triage, pr_reviewer, issue_handler, daily_planner

    settings = Settings()
    state = StateManager("data/state.json")
    notifier = Notifier(ntfy_topic=settings.ntfy_topic, slack_user_id=settings.slack_user_id, agent_secret=settings.agent_secret)
    bg_runner = BackgroundTaskRunner()

    common = dict(
        state=state,
        notifier=notifier,
        skills_path=settings.skills_path,
        repos_path=settings.repos_path,
        settings=settings,
    )

    slack_triage = SlackTriage(
        **common,
        slack_user_id=settings.slack_user_id,
        jira_email=settings.jira_email,
    )
    pr_reviewer = PRReviewer(**common, memory_path=settings.memory_path)
    issue_handler = IssueHandler(**common, memory_path=settings.memory_path, jira_email=settings.jira_email)
    daily_planner = DailyPlanner(**common, vault_path=settings.obsidian_vault_path, jira_email=settings.jira_email)

    yield


app = FastAPI(title="Divyanshu Agent", lifespan=lifespan)


# Auth middleware
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    import os
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)
    secret = settings.agent_secret if settings is not None else os.environ.get("AGENT_SECRET", "")
    if request.headers.get("Authorization") != f"Bearer {secret}":
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)


# --- Models ---

class PRReviewRequest(BaseModel):
    pr_url: str
    slack_thread: dict | None = None


class HandleRequest(BaseModel):
    description: str
    source: dict | None = None


# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    _state = state if state is not None else StateManager("data/state.json")
    _bg_runner = bg_runner if bg_runner is not None else BackgroundTaskRunner()
    pending = await _state.get_pending_approvals()
    active_tasks = [
        {
            "task_id": t.task_id,
            "state": t.state,
            "description": t.description,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "error": t.error,
        }
        for t in _bg_runner.get_all_statuses()
    ]
    return {
        "pending_approvals": pending,
        "background_tasks": active_tasks,
    }


@app.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    cancelled = await bg_runner.cancel(task_id)
    return {"cancelled": cancelled, "task_id": task_id}


class BackgroundFlag(BaseModel):
    background: bool = False


@app.post("/run/all")
async def run_all(flag: BackgroundFlag = BackgroundFlag()):
    async def _run_all():
        slack_result = await slack_triage.run()
        pr_results = []
        for pr in slack_result.get("pr_reviews", []):
            result = await pr_reviewer.run(pr_url=pr["url"], slack_thread=pr.get("slack_thread"))
            pr_results.append(result)
        plan_result = await daily_planner.plan_day(slack_results=str(slack_result))
        return {"slack": slack_result, "pr_reviews": pr_results, "plan": plan_result}

    if flag.background:
        import uuid
        task_id = f"run-all-{uuid.uuid4().hex[:8]}"
        await bg_runner.submit(task_id, _run_all(), description="Full cycle: Slack + PR reviews + daily plan")
        return {"task_id": task_id, "status": "dispatched"}

    return await _run_all()


@app.post("/run/slack")
async def run_slack():
    result = await slack_triage.run()
    return result


@app.post("/run/review-pr")
async def run_review_pr(request: PRReviewRequest):
    result = await pr_reviewer.run(pr_url=request.pr_url, slack_thread=request.slack_thread)
    return result


@app.post("/run/handle")
async def run_handle(request: HandleRequest, flag: BackgroundFlag = BackgroundFlag()):
    issue_id = await issue_handler.create_issue(
        description=request.description,
        source=request.source or {},
    )

    if flag.background:
        await bg_runner.submit(
            f"handle-{issue_id[:8]}",
            issue_handler.run_phase1(issue_id),
            description=f"Investigating: {request.description[:80]}",
        )
        return {"issue_id": issue_id, "task_id": f"handle-{issue_id[:8]}", "status": "dispatched"}

    result = await issue_handler.run_phase1(issue_id)
    return {"issue_id": issue_id, **result}


@app.post("/run/handle/{issue_id}/phase2")
async def run_handle_phase2(issue_id: str):
    result = await issue_handler.run_phase2(issue_id)
    return result


@app.post("/run/handle/{issue_id}/phase3")
async def run_handle_phase3(issue_id: str):
    result = await issue_handler.run_phase3(issue_id)
    return result


@app.post("/run/handle/{issue_id}/phase4")
async def run_handle_phase4(issue_id: str):
    result = await issue_handler.run_phase4(issue_id)
    return result


@app.post("/run/plan-day")
async def run_plan_day():
    result = await daily_planner.plan_day()
    return result


@app.post("/run/end-day")
async def run_end_day():
    result = await daily_planner.end_day()
    return result


@app.post("/approve/{task_id}")
async def approve_task(task_id: str):
    _state = state if state is not None else StateManager("data/state.json")
    try:
        approval = await _state.approve(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No pending approval with id: {task_id}")
    result = await _execute_approved_action(approval)
    return {"status": "approved", "result": result}


async def _execute_approved_action(approval: dict) -> dict:
    """Execute the approved action. Uses issue_id from approval payload."""
    issue_id = approval.get("payload", {}).get("issue_id")

    if approval["type"] == "jira_ticket" and issue_id:
        return await issue_handler.run_phase2(issue_id)
    elif approval["type"] == "plan_approval" and issue_id:
        return await issue_handler.run_phase3(issue_id)
    elif approval["type"] == "pr_creation" and issue_id:
        return await issue_handler.run_phase4(issue_id)
    elif approval["type"] == "slack_reply":
        # Slack reply approval — actually send the drafted message
        payload = approval.get("payload", {})
        channel_id = payload.get("channel_id")
        text = payload.get("text")
        thread_ts = payload.get("thread_ts")
        if channel_id and text:
            import httpx
            _settings = settings if settings is not None else Settings()
            token = _settings.slack_user_token or _settings.slack_bot_token
            data = {"channel": channel_id, "text": text}
            if thread_ts:
                data["thread_ts"] = thread_ts
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json=data,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                result = resp.json()
                if result.get("ok"):
                    return {"action": "slack_reply_sent", "channel": channel_id}
                return {"action": "slack_reply_failed", "error": result.get("error")}
        return {"action": "slack_reply_missing_data"}

    return {"action": "approved_no_followup"}


@app.post("/reject/{task_id}")
async def reject_task(task_id: str):
    approval = await state.reject(task_id)
    return {"status": "rejected", "approval": approval}
