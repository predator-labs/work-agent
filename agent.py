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
    notifier = Notifier(ntfy_topic=settings.ntfy_topic, slack_user_id=settings.slack_user_id, agent_secret=settings.agent_secret)

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
                result = await deps["pr"].run(pr_url=pr["url"], slack_thread=pr.get("slack_thread"))
                if result.get("skipped"):
                    typer.echo(f"  Skipped: {result['reason']}")

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

    # Track recently handled events to prevent duplicates
    _handled_events: dict[str, float] = {}

    async def _get_user_name(user_id: str) -> str:
        """Look up Slack user's first name."""
        import httpx
        token = deps["settings"].slack_user_token or deps["settings"].slack_bot_token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://slack.com/api/users.info",
                params={"user": user_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            return data.get("user", {}).get("real_name", user_id)

    async def _send_slack_reply(channel: str, text: str, thread_ts: str = ""):
        """Send a Slack message."""
        import httpx
        token = deps["settings"].slack_user_token or deps["settings"].slack_bot_token
        data = {"channel": channel, "text": text}
        if thread_ts:
            data["thread_ts"] = thread_ts
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                json=data,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )

    def _is_casual_message(text: str) -> bool:
        """Check if a message is casual/conversational (not work-related)."""
        cleaned = text.strip().lower()
        # Pure greetings
        greetings = ["hello", "hi", "hey", "hellu", "helu", "sup", "yo", "ping", "good morning", "gm"]
        for g in greetings:
            if cleaned.startswith(g):
                remaining = cleaned[len(g):].strip(" !.,;:\n")
                if len(remaining) < 15 and "?" not in remaining:
                    return True
        # Casual questions with no work keywords
        casual_patterns = [
            "how are you", "how r u", "how you doing", "what's up", "whats up",
            "wassup", "kaise ho", "kya haal", "kuch aur", "aur bata",
        ]
        if any(p in cleaned for p in casual_patterns):
            work_keywords = ["ticket", "pr ", "pull request", "bug", "fix", "deploy", "release",
                           "jira", "es-", "eng-", "issue", "review", "status", "check"]
            if not any(w in cleaned for w in work_keywords):
                return True
        return False

    async def on_dm(event):
        """Handle DM events — instant reply for casual, targeted response for work messages."""
        import time
        user_id = event.get("user", "?")
        text = event.get("text", "")
        channel = event.get("channel", "")
        ts = event.get("ts", "")

        # Deduplicate: skip if we handled this exact message recently
        event_key = f"{channel}:{ts}"
        now = time.time()
        if event_key in _handled_events and now - _handled_events[event_key] < 10:
            return
        _handled_events[event_key] = now
        # Clean old entries
        for k in list(_handled_events):
            if now - _handled_events[k] > 60:
                del _handled_events[k]

        logging.info(f"DM from {user_id}: {text[:100]}")

        # Ignore junk: single characters, empty messages, random keystrokes
        cleaned_text = text.strip()
        if len(cleaned_text) < 3:
            logging.info(f"Ignoring short message: \"{cleaned_text}\"")
            return

        name = await _get_user_name(user_id)
        first_name = name.split()[0]

        # Casual messages: auto-reply instantly
        if _is_casual_message(text):
            reply = f"Hey {first_name}! Doing well, thanks for asking! How can I help you?"
            await _send_slack_reply(channel, reply)
            logging.info(f"Auto-replied to {name}: {reply}")
            return

        # Work-related DM: ack first, then research and reply
        import httpx as _httpx
        from claude_agent_sdk import query, ClaudeAgentOptions
        from shared.stream_output import create_renderer
        from shared.custom_tools import build_custom_tools_server
        from config.mcp import build_mcp_servers

        # Send immediate acknowledgment
        await _send_slack_reply(channel, f"Let me check on that, {first_name}. One moment...")
        logging.info(f"Ack sent to {name}")

        renderer = create_renderer(f"DM from {first_name}")

        # Fetch recent conversation history for context
        token = deps["settings"].slack_user_token or deps["settings"].slack_bot_token
        conversation_context = ""
        try:
            async with _httpx.AsyncClient() as client:
                import time as _time
                oldest = str(_time.time() - 2 * 86400)  # last 2 days
                resp = await client.get(
                    "https://slack.com/api/conversations.history",
                    params={"channel": channel, "limit": "15", "oldest": oldest},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                history = resp.json()
                if history.get("ok"):
                    messages = history.get("messages", [])
                    lines = []
                    for m in reversed(messages):
                        sender = "Divyanshu" if m.get("user") == deps["settings"].slack_user_id else first_name
                        lines.append(f"{sender}: {m.get('text', '')}")
                    conversation_context = "\n".join(lines)
        except Exception:
            pass

        # Build MCP servers for Jira, Bitbucket etc.
        servers = {}
        if deps["settings"]:
            servers = build_mcp_servers(deps["settings"])
        servers["agent-tools"] = build_custom_tools_server(
            deps["state"], deps["slack"].notifier,
            slack_user_token=deps["settings"].slack_user_token,
            slack_bot_token=deps["settings"].slack_bot_token,
            jira_url=deps["settings"].jira_url,
            jira_email=deps["settings"].jira_email,
            jira_api_token=deps["settings"].jira_api_token,
        )

        system = (
            f"You are Divyanshu Sharma, AI/ML engineer at Docyt. "
            f"{name} is messaging you on Slack DM.\n"
            f"Divyanshu's Jira email: {deps['settings'].jira_email}\n\n"
            f"CONVERSATION HISTORY (most recent at bottom):\n{conversation_context}\n\n"
            f"RULES:\n"
            f"- Read the conversation history to understand context.\n"
            f"- If the question needs real data (Jira tickets, PR status, etc.), "
            f"use jira_search or jira_get_issue tools to look it up.\n"
            f"- For Jira queries, use jira_search with JQL like: "
            f"'assignee = \"{deps['settings'].jira_email}\" ORDER BY updated DESC'\n"
            f"- Available tools: jira_search, jira_get_issue, slack_search_messages\n"
            f"- Your FINAL output must be ONLY the reply text to send on Slack.\n"
            f"- Keep it concise and natural — like how a real engineer would reply.\n"
            f"- Do NOT use slack_send_message tool. Just output the text.\n"
            f"- No markdown, no quotes, no preamble. Just the message.\n\n"
            f"TONE & LANGUAGE:\n"
            f"- Always be respectful and professional.\n"
            f"- When replying in Hindi/Hinglish, ALWAYS use 'aap' (respectful), NEVER use 'tu' or 'tum'.\n"
            f"- Address colleagues with respect — they are your peers and seniors.\n"
            f"- Match the language of the incoming message (English reply for English, Hinglish for Hindi).\n"
            f"- Be warm and helpful but never overly casual or disrespectful."
        )

        draft_reply = ""
        last_text = ""
        async for message in query(
            prompt=f"Reply to {name}'s latest message:\n\"{text}\"",
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": system},
                mcp_servers=servers,
                allowed_tools=[
                    "mcp__agent-tools__*",
                    "mcp__atlassian__*",
                    "mcp__bitbucket__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=10,
            ),
        ):
            renderer.render(message)
            if hasattr(message, "result") and message.result:
                draft_reply = message.result.strip()
            # Also capture text blocks from assistant messages as fallback
            if hasattr(message, "content"):
                for block in message.content:
                    if hasattr(block, "text") and block.text.strip():
                        last_text = block.text.strip()

        # Use draft_reply if available, otherwise fall back to last text output
        reply = draft_reply or last_text
        if reply:
            # Clean up: remove any "Here's the reply:" preamble
            for prefix in ["Here's the reply:", "Here is the reply:", "Reply:", "Draft:"]:
                if reply.startswith(prefix):
                    reply = reply[len(prefix):].strip()
            await _send_slack_reply(channel, reply)
            logging.info(f"Replied to {name}: {reply[:100]}")
        else:
            # Fallback: at least acknowledge
            fallback = f"Hey {first_name}, let me look into this and get back to you shortly."
            await _send_slack_reply(channel, fallback)
            logging.info(f"Sent fallback reply to {name}")

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
