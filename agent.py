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
            pr_count = len(slack_result.get("pr_reviews", []))
            issue_count = len(slack_result.get("issues", []))
            simple_count = len(slack_result.get("simple", []))
            info_count = len(slack_result.get("informational", []))
            total = pr_count + issue_count + simple_count + info_count

            if total > 0:
                typer.echo(f"Slack: {total} items — {pr_count} PRs, {issue_count} issues, {simple_count} replies, {info_count} FYI")
                for pr in slack_result.get("pr_reviews", []):
                    typer.echo(f"  PR: {pr.get('url', '?')} (from {pr.get('requester', '?')})")
                for issue in slack_result.get("issues", []):
                    typer.echo(f"  Issue [{issue.get('priority', '?')}]: {issue.get('description', '?')[:100]}")
            elif slack_result.get("raw_result"):
                typer.echo(f"Slack triage complete:\n{slack_result['raw_result'][:2000]}")
            else:
                typer.echo("Slack: no actionable messages found")

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
            payload = approval.get("payload", {})
            channel_id = payload.get("channel_id")
            text = payload.get("text")
            thread_ts = payload.get("thread_ts")
            if channel_id and text:
                import httpx
                token = deps["settings"].slack_user_token or deps["settings"].slack_bot_token
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
                        typer.echo(f"Slack reply sent to {channel_id}")
                    else:
                        typer.echo(f"Failed to send reply: {result.get('error')}")
            else:
                typer.echo("Slack reply approved but missing channel/text data.")

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
def listen():
    """Start event-driven mode: Slack (real-time) + Jira (polling) + periodic triage."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    deps = _get_deps()

    async def on_mention(event):
        """Handle @mention events."""
        text = event.get("text", "")
        channel = event.get("channel", "")
        thread_ts = event.get("ts", "")
        user = event.get("user", "")

        # Check if it's a PR link
        if "bitbucket.org" in text and "pull-requests" in text:
            import re
            match = re.search(r"https://bitbucket\.org/[^\s]+/pull-requests/\d+", text)
            if match:
                pr_url = match.group(0)
                logging.info(f"PR review triggered: {pr_url}")
                await deps["pr"].run(pr_url=pr_url, slack_thread={"channel_id": channel, "thread_ts": thread_ts})
                return

        # Otherwise treat as a message to triage
        result = await deps["slack"].run()
        logging.info(f"Mention triage: {len(result.get('pr_reviews', []))} PRs, {len(result.get('issues', []))} issues")

    async def on_dm(event):
        """Handle DM events — quick reply for simple messages, full triage for complex ones."""
        user_id = event.get("user", "?")
        text = event.get("text", "")
        channel = event.get("channel", "")
        ts = event.get("ts", "")
        logging.info(f"DM from {user_id}: {text[:100]}")

        # For simple greetings ONLY (no question or extra content), reply directly
        simple_patterns = ["hello", "hi", "hey", "hellu", "helu", "sup", "yo", "ping", "good morning", "gm"]
        cleaned = text.strip().lower()
        # Strip greeting prefix to check if there's real content after it
        remaining = cleaned
        for p in simple_patterns:
            if cleaned.startswith(p):
                remaining = cleaned[len(p):].strip(" !.,;:\n")
                break
        is_pure_greeting = any(cleaned.startswith(p) for p in simple_patterns) and len(remaining) < 15 and "?" not in text
        if is_pure_greeting:
            import httpx
            token = deps["settings"].slack_user_token or deps["settings"].slack_bot_token
            # Look up user name
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://slack.com/api/users.info",
                    params={"user": user_id},
                    headers={"Authorization": f"Bearer {token}"},
                )
                user_data = resp.json()
                name = user_data.get("user", {}).get("real_name", user_id)

                reply = f"Hey {name.split()[0]}! What's up?"
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json={"channel": channel, "text": reply},
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
            logging.info(f"Auto-replied to {name}: {reply}")
            return

        # For anything else, run full triage
        result = await deps["slack"].run()
        logging.info(f"DM triage complete: {len(result.get('simple', []))} replies drafted")

    async def on_pr_link(event):
        """Handle PR links shared in channels."""
        import re
        text = event.get("text", "")
        channel = event.get("channel", "")
        thread_ts = event.get("ts", "")
        match = re.search(r"https://bitbucket\.org/[^\s>]+/pull-requests/\d+", text)
        if match:
            pr_url = match.group(0)
            logging.info(f"PR link detected: {pr_url}")
            await deps["pr"].run(pr_url=pr_url, slack_thread={"channel_id": channel, "thread_ts": thread_ts})

    async def on_full_triage():
        """Periodic full triage fallback."""
        result = await deps["slack"].run()
        pr_count = len(result.get("pr_reviews", []))
        issue_count = len(result.get("issues", []))
        simple_count = len(result.get("simple", []))
        logging.info(f"Full triage: {pr_count} PRs, {issue_count} issues, {simple_count} replies")

        for pr in result.get("pr_reviews", []):
            await deps["pr"].run(pr_url=pr["url"], slack_thread=pr.get("slack_thread"))

    from capabilities.event_listener import EventListener
    listener = EventListener(
        settings=deps["settings"],
        state=deps["state"],
        notifier=deps["slack"].notifier,
        on_mention=on_mention,
        on_dm=on_dm,
        on_pr_link=on_pr_link,
        on_full_triage=on_full_triage,
    )

    async def _run():
        from shared.caffeinate import CaffeinateGuard
        with CaffeinateGuard():
            await listener.start()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\nShutting down...")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run("server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
