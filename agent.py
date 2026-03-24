# agent.py
import asyncio

import typer

app = typer.Typer(name="agent", help="Divyanshu's personal autonomous agent")


def _get_deps():
    """Lazy-load dependencies to avoid import-time env var requirements."""
    from config.settings import Settings
    from shared.state import StateManager
    from shared.notifications import Notifier
    from capabilities.slack_triage import SlackTriage
    from capabilities.pr_reviewer import PRReviewer
    from capabilities.issue_handler import IssueHandler
    from capabilities.daily_planner import DailyPlanner

    settings = Settings()
    state = StateManager("data/state.json")
    notifier = Notifier(ntfy_topic=settings.ntfy_topic, slack_user_id=settings.slack_user_id)

    common = dict(
        state=state, notifier=notifier,
        skills_path=settings.skills_path, repos_path=settings.repos_path,
        settings=settings,
    )

    return {
        "settings": settings,
        "state": state,
        "slack": SlackTriage(**common, slack_user_id=settings.slack_user_id, jira_email=settings.jira_email),
        "pr": PRReviewer(**common, memory_path=settings.memory_path),
        "issue": IssueHandler(**common, memory_path=settings.memory_path, jira_email=settings.jira_email),
        "planner": DailyPlanner(**common, vault_path=settings.obsidian_vault_path, jira_email=settings.jira_email),
    }


@app.command()
def run_all(background: bool = typer.Option(False, "--bg", help="Run in background, return immediately")):
    """Full cycle: Slack triage + PR reviews + daily plan."""
    if background:
        import httpx
        from config.settings import Settings
        settings = Settings()
        resp = httpx.post(
            "http://127.0.0.1:8000/run/all",
            json={"background": True},
            headers={"Authorization": f"Bearer {settings.agent_secret}"},
        )
        data = resp.json()
        typer.echo(f"Dispatched: {data.get('task_id')} — check status with `agent status`")
        return

    deps = _get_deps()

    async def _run():
        from shared.caffeinate import CaffeinateGuard
        with CaffeinateGuard():
            # 1. Slack triage
            typer.echo("Running Slack triage...")
            slack_result = await deps["slack"].run()
            typer.echo(f"Slack: {len(slack_result.get('simple', []))} messages triaged")

            # 2. Process any PR review requests found in Slack
            for pr in slack_result.get("pr_reviews", []):
                typer.echo(f"Reviewing PR: {pr.get('url', 'unknown')}")
                await deps["pr"].run(pr_url=pr["url"], slack_thread=pr.get("slack_thread"))

            # 3. Daily plan
            await deps["planner"].plan_day(slack_results=str(slack_result))
            typer.echo("Daily plan created.")

    asyncio.run(_run())


@app.command()
def slack():
    """Triage Slack messages."""
    deps = _get_deps()
    result = asyncio.run(deps["slack"].run())
    typer.echo(f"Triage complete: {result}")


@app.command()
def review_pr(pr_url: str):
    """Review a Bitbucket pull request."""
    deps = _get_deps()
    result = asyncio.run(deps["pr"].run(pr_url=pr_url))
    typer.echo(f"Review complete: {result}")


@app.command()
def handle(
    description: str,
    background: bool = typer.Option(False, "--bg", help="Run in background"),
):
    """Handle an issue or feature request."""
    if background:
        import httpx
        from config.settings import Settings
        settings = Settings()
        resp = httpx.post(
            "http://127.0.0.1:8000/run/handle",
            json={"description": description, "background": True},
            headers={"Authorization": f"Bearer {settings.agent_secret}"},
        )
        data = resp.json()
        typer.echo(f"Dispatched: {data.get('task_id')} — check status with `agent status`")
        return

    deps = _get_deps()

    async def _run():
        from shared.caffeinate import CaffeinateGuard
        with CaffeinateGuard():
            issue_id = await deps["issue"].create_issue(description, source={"cli": True})
            typer.echo(f"Issue created: {issue_id}")
            result = await deps["issue"].run_phase1(issue_id)
            typer.echo("Phase 1 complete. Awaiting approval.")
            return result

    asyncio.run(_run())


@app.command()
def plan_day():
    """Generate morning daily plan."""
    deps = _get_deps()
    result = asyncio.run(deps["planner"].plan_day())
    typer.echo(f"Daily plan created: {result}")


@app.command()
def end_day():
    """Generate end-of-day summary."""
    deps = _get_deps()
    result = asyncio.run(deps["planner"].end_day())
    typer.echo(f"End-of-day summary: {result}")


@app.command()
def approve(task_id: str):
    """Approve a pending action and execute the next phase."""
    deps = _get_deps()

    async def _approve():
        approval = await deps["state"].approve(task_id)
        typer.echo(f"Approved: {task_id} ({approval['type']})")

        # Trigger downstream phase based on approval type
        issue_id = approval.get("payload", {}).get("issue_id")
        if approval["type"] == "jira_ticket" and issue_id:
            typer.echo("Starting Phase 2: Brainstorm & Plan...")
            await deps["issue"].run_phase2(issue_id)
        elif approval["type"] == "plan_approval" and issue_id:
            typer.echo("Starting Phase 3: Implement & Test...")
            await deps["issue"].run_phase3(issue_id)
        elif approval["type"] == "pr_creation" and issue_id:
            typer.echo("Starting Phase 4: Create PR & Notify...")
            await deps["issue"].run_phase4(issue_id)
        elif approval["type"] == "slack_reply":
            typer.echo("Slack reply will be sent.")

    asyncio.run(_approve())


@app.command()
def reject(task_id: str):
    """Reject a pending action."""
    deps = _get_deps()
    asyncio.run(deps["state"].reject(task_id))
    typer.echo(f"Rejected: {task_id}")


@app.command()
def status():
    """Show pending approvals and in-progress tasks."""
    deps = _get_deps()
    pending = asyncio.run(deps["state"].get_pending_approvals())
    if not pending:
        typer.echo("No pending approvals.")
    else:
        typer.echo(f"{len(pending)} pending approval(s):")
        for p in pending:
            typer.echo(f"  [{p['type']}] {p['task_id']} — created {p['created_at']}")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run("server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
