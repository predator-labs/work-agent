from typing import Any
from claude_agent_sdk import tool, create_sdk_mcp_server
from shared.state import StateManager
from shared.notifications import Notifier


def build_custom_tools_server(state: StateManager, notifier: Notifier, vault_path: str = "/vault"):

    @tool(
        "create_approval",
        "Create a pending approval request. Use this when an action needs Divyanshu's approval before executing.",
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique ID for this approval"},
                "approval_type": {"type": "string", "enum": ["slack_reply", "jira_ticket", "plan_approval", "pr_creation"]},
                "action_summary": {"type": "string", "description": "What will happen on approval"},
                "details": {"type": "string", "description": "Full details of the pending action"},
                "payload": {"type": "object", "description": "Data needed to execute the action"},
                "context": {"type": "object", "description": "Slack thread, channel, etc."},
            },
            "required": ["task_id", "approval_type", "action_summary", "details", "payload"],
        },
    )
    async def create_approval(args: dict[str, Any]) -> dict[str, Any]:
        try:
            await state.add_pending_approval(
                task_id=args["task_id"],
                approval_type=args["approval_type"],
                payload=args["payload"],
                context=args.get("context", {}),
            )
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error saving approval to state: {e}"}]}

        try:
            await notifier.push(
                message=f"{args['action_summary']}\nTask: {args['task_id']}",
                title="Approval Required",
                priority="high",
                tags="warning",
            )
        except Exception as e:
            # Notification failure is non-fatal — approval was already saved
            pass

        try:
            msg = notifier.format_approval_message(
                task_id=args["task_id"],
                action=args["action_summary"],
                details=args["details"],
            )
        except Exception as e:
            msg = f"Approval ID: {args['task_id']}\nAction: {args['action_summary']}"

        return {"content": [{"type": "text", "text": f"Approval created: {args['task_id']}\n\nSlack DM message:\n{msg}"}]}

    @tool(
        "send_notification",
        "Send a push notification to Divyanshu's phone via ntfy.sh.",
        {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "title": {"type": "string"},
                "priority": {"type": "string", "enum": ["min", "low", "default", "high", "max"]},
            },
            "required": ["message"],
        },
    )
    async def send_notification(args: dict[str, Any]) -> dict[str, Any]:
        try:
            await notifier.push(
                message=args["message"],
                title=args.get("title", "Work Agent"),
                priority=args.get("priority", "default"),
            )
            return {"content": [{"type": "text", "text": f"Notification sent: {args['message']}"}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error sending notification: {e}"}]}

    @tool(
        "log_to_obsidian",
        "Append an entry to today's Obsidian daily log.",
        {
            "type": "object",
            "properties": {
                "entry": {"type": "string", "description": "The log entry text"},
                "section": {"type": "string", "enum": ["Tasks Completed", "PRs Created", "Slack Messages Handled", "Pending"]},
            },
            "required": ["entry", "section"],
        },
    )
    async def log_to_obsidian(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from datetime import datetime, timezone
            from pathlib import Path

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            time_now = datetime.now(timezone.utc).strftime("%H:%M")
            log_dir = Path(vault_path) / "daily-logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{today}.md"

            if not log_file.exists():
                log_file.write_text(
                    f"# {today} — Daily Log\n\n"
                    "## Tasks Completed\n\n"
                    "## PRs Created\n\n"
                    "## Slack Messages Handled\n\n"
                    "## Pending\n\n"
                )

            content = log_file.read_text()
            section_header = f"## {args['section']}"
            entry_line = f"- [{time_now}] {args['entry']}\n"

            if section_header in content:
                content = content.replace(section_header + "\n", section_header + "\n" + entry_line)
            else:
                content += f"\n{section_header}\n{entry_line}"

            log_file.write_text(content)
            return {"content": [{"type": "text", "text": f"Logged to {log_file}: {args['entry']}"}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error logging to Obsidian: {e}"}]}

    return create_sdk_mcp_server(
        name="agent-tools",
        version="1.0.0",
        tools=[create_approval, send_notification, log_to_obsidian],
    )
