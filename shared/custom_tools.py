from typing import Any
from claude_agent_sdk import tool, create_sdk_mcp_server, SdkMcpTool
from shared.state import StateManager
from shared.notifications import Notifier

# Module-level cache for the SDK MCP server instance.
# The SDK MCP server must be created once and reused across query() calls.
# Creating a new server instance per query() causes "stream closed" errors
# because the SDK registers the server transport on first use, and a
# re-created Server object gets a stale/closed transport reference.
_cached_server = None
_cached_server_key = None


def build_custom_tools_server(
    state: StateManager,
    notifier: Notifier,
    vault_path: str = "/vault",
    slack_user_token: str = "",
    slack_bot_token: str = "",
    jira_url: str = "",
    jira_email: str = "",
    jira_api_token: str = "",
):
    global _cached_server, _cached_server_key

    cache_key = (id(state), id(notifier), vault_path, slack_user_token, slack_bot_token, jira_url)
    if _cached_server is not None and _cached_server_key == cache_key:
        return _cached_server

    import httpx

    # Prefer user token for reading (full access), bot token for posting
    slack_read_token = slack_user_token or slack_bot_token
    slack_write_token = slack_bot_token or slack_user_token

    async def _slack_api(method: str, params: dict | None = None, token: str | None = None) -> dict:
        """Call Slack Web API."""
        t = token or slack_read_token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://slack.com/api/{method}",
                params=params or {},
                headers={"Authorization": f"Bearer {t}"},
                timeout=30,
            )
            return resp.json()

    async def _slack_api_post(method: str, json_data: dict, token: str | None = None) -> dict:
        """Call Slack Web API with POST."""
        t = token or slack_write_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://slack.com/api/{method}",
                json=json_data,
                headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json"},
                timeout=30,
            )
            return resp.json()

    async def _jira_api(endpoint: str, params: dict | None = None) -> dict:
        """Call Jira REST API."""
        if not jira_url or not jira_api_token:
            return {"error": "Jira not configured"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{jira_url}{endpoint}",
                params=params or {},
                auth=(jira_email, jira_api_token),
                timeout=30,
            )
            return resp.json()

    tools = _build_tools(
        state, notifier, vault_path,
        _slack_api, _slack_api_post, slack_read_token, slack_write_token,
        _jira_api, jira_email,
    )

    server = create_sdk_mcp_server(
        name="agent-tools",
        version="1.0.0",
        tools=tools,
    )
    _cached_server = server
    _cached_server_key = cache_key
    return server


def _build_tools(
    state: StateManager,
    notifier: Notifier,
    vault_path: str,
    _slack_api,
    _slack_api_post,
    slack_read_token: str,
    slack_write_token: str,
    _jira_api=None,
    jira_email: str = "",
) -> list[SdkMcpTool]:
    """Build and return all SdkMcpTool instances."""

    # ── Slack Tools ──

    @tool(
        "slack_list_conversations",
        "List Slack conversations (DMs, channels, group DMs). Use types parameter to filter.",
        {
            "type": "object",
            "properties": {
                "types": {
                    "type": "string",
                    "description": "Comma-separated: im, mpim, public_channel, private_channel. Default: im,mpim,public_channel,private_channel",
                    "default": "im,mpim,public_channel,private_channel",
                },
                "limit": {"type": "number", "description": "Max results (default 100)", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
        },
    )
    async def slack_list_conversations(args: dict[str, Any]) -> dict[str, Any]:
        params = {
            "types": args.get("types", "im,mpim,public_channel,private_channel"),
            "limit": str(args.get("limit", 100)),
            "exclude_archived": "true",
        }
        if args.get("cursor"):
            params["cursor"] = args["cursor"]
        result = await _slack_api("conversations.list", params)
        if not result.get("ok"):
            return {"content": [{"type": "text", "text": f"Error: {result.get('error')}"}]}
        channels = result.get("channels", [])
        summary = []
        for ch in channels:
            ch_type = "DM" if ch.get("is_im") else "Group DM" if ch.get("is_mpim") else "Channel"
            name = ch.get("name") or ch.get("user") or ch.get("id")
            summary.append({"id": ch["id"], "name": name, "type": ch_type, "is_member": ch.get("is_member", False)})
        return {"content": [{"type": "text", "text": str({"channels": summary, "next_cursor": result.get("response_metadata", {}).get("next_cursor", "")})}]}

    @tool(
        "slack_get_history",
        "Get recent messages from a Slack channel/DM. Returns messages in reverse chronological order.",
        {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel/DM ID"},
                "limit": {"type": "number", "description": "Max messages (default 20)", "default": 20},
                "oldest": {"type": "string", "description": "Unix timestamp — only get messages after this time"},
            },
            "required": ["channel_id"],
        },
    )
    async def slack_get_history(args: dict[str, Any]) -> dict[str, Any]:
        params = {"channel": args["channel_id"], "limit": str(args.get("limit", 20))}
        if args.get("oldest"):
            params["oldest"] = args["oldest"]
        result = await _slack_api("conversations.history", params)
        if not result.get("ok"):
            return {"content": [{"type": "text", "text": f"Error: {result.get('error')}"}]}
        messages = []
        for m in result.get("messages", []):
            messages.append({
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "ts": m.get("ts", ""),
                "thread_ts": m.get("thread_ts"),
                "reply_count": m.get("reply_count", 0),
                "type": m.get("subtype", "message"),
            })
        return {"content": [{"type": "text", "text": str({"messages": messages, "has_more": result.get("has_more", False)})}]}

    @tool(
        "slack_get_thread",
        "Get all replies in a Slack thread.",
        {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel ID"},
                "thread_ts": {"type": "string", "description": "Thread timestamp"},
            },
            "required": ["channel_id", "thread_ts"],
        },
    )
    async def slack_get_thread(args: dict[str, Any]) -> dict[str, Any]:
        params = {"channel": args["channel_id"], "ts": args["thread_ts"]}
        result = await _slack_api("conversations.replies", params)
        if not result.get("ok"):
            return {"content": [{"type": "text", "text": f"Error: {result.get('error')}"}]}
        messages = [{"user": m.get("user", ""), "text": m.get("text", ""), "ts": m.get("ts", "")} for m in result.get("messages", [])]
        return {"content": [{"type": "text", "text": str({"messages": messages})}]}

    @tool(
        "slack_search_messages",
        "Search Slack messages. Requires user token (xoxp). Supports Slack search syntax.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g., 'from:@user', 'in:#channel', 'has:link')"},
                "count": {"type": "number", "description": "Max results (default 20)", "default": 20},
                "sort": {"type": "string", "description": "Sort by: score or timestamp", "default": "timestamp"},
            },
            "required": ["query"],
        },
    )
    async def slack_search_messages(args: dict[str, Any]) -> dict[str, Any]:
        params = {
            "query": args["query"],
            "count": str(args.get("count", 20)),
            "sort": args.get("sort", "timestamp"),
        }
        result = await _slack_api("search.messages", params, token=slack_read_token)
        if not result.get("ok"):
            return {"content": [{"type": "text", "text": f"Error: {result.get('error')}"}]}
        matches = result.get("messages", {}).get("matches", [])
        messages = []
        for m in matches:
            messages.append({
                "user": m.get("user", m.get("username", "")),
                "text": m.get("text", "")[:500],
                "ts": m.get("ts", ""),
                "channel": {"id": m.get("channel", {}).get("id", ""), "name": m.get("channel", {}).get("name", "")},
                "permalink": m.get("permalink", ""),
            })
        return {"content": [{"type": "text", "text": str({"total": result.get("messages", {}).get("total", 0), "messages": messages})}]}

    @tool(
        "slack_send_message",
        "Send a message to a Slack channel or DM.",
        {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel or DM ID"},
                "text": {"type": "string", "description": "Message text"},
                "thread_ts": {"type": "string", "description": "Thread timestamp to reply in thread"},
            },
            "required": ["channel_id", "text"],
        },
    )
    async def slack_send_message(args: dict[str, Any]) -> dict[str, Any]:
        data = {"channel": args["channel_id"], "text": args["text"]}
        if args.get("thread_ts"):
            data["thread_ts"] = args["thread_ts"]
        result = await _slack_api_post("chat.postMessage", data, token=slack_write_token)
        if not result.get("ok"):
            return {"content": [{"type": "text", "text": f"Error: {result.get('error')}"}]}
        return {"content": [{"type": "text", "text": f"Message sent to {args['channel_id']}"}]}

    @tool(
        "slack_get_user_info",
        "Get info about a Slack user by their ID.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Slack user ID"},
            },
            "required": ["user_id"],
        },
    )
    async def slack_get_user_info(args: dict[str, Any]) -> dict[str, Any]:
        result = await _slack_api("users.info", {"user": args["user_id"]})
        if not result.get("ok"):
            return {"content": [{"type": "text", "text": f"Error: {result.get('error')}"}]}
        u = result.get("user", {})
        return {"content": [{"type": "text", "text": str({
            "id": u.get("id"), "name": u.get("name"), "real_name": u.get("real_name"),
            "display_name": u.get("profile", {}).get("display_name"),
        })}]}

    # ── Agent Tools ──

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
        except Exception:
            pass

        try:
            msg = notifier.format_approval_message(
                task_id=args["task_id"],
                action=args["action_summary"],
                details=args["details"],
            )
        except Exception:
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

    # ── Jira Tools ──

    @tool(
        "jira_search",
        "Search Jira issues using JQL. Returns key, summary, status, priority, assignee.",
        {
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL query string"},
                "max_results": {"type": "number", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["jql"],
        },
    )
    async def jira_search(args: dict[str, Any]) -> dict[str, Any]:
        if not _jira_api:
            return {"content": [{"type": "text", "text": "Jira not configured"}]}
        result = await _jira_api(
            "/rest/api/3/search/jql",
            {"jql": args["jql"], "maxResults": str(args.get("max_results", 10)), "fields": "summary,status,priority,assignee,updated"},
        )
        if "error" in result or "errorMessages" in result:
            return {"content": [{"type": "text", "text": f"Jira error: {result}"}]}
        issues = []
        for issue in result.get("issues", []):
            f = issue.get("fields", {})
            issues.append({
                "key": issue["key"],
                "summary": f.get("summary", ""),
                "status": f.get("status", {}).get("name", ""),
                "priority": f.get("priority", {}).get("name", ""),
                "assignee": f.get("assignee", {}).get("displayName", "") if f.get("assignee") else "Unassigned",
                "updated": f.get("updated", ""),
            })
        return {"content": [{"type": "text", "text": str({"total": result.get("total", 0), "issues": issues})}]}

    @tool(
        "jira_get_issue",
        "Get details of a specific Jira issue by key (e.g., ENG-1234, ES-5841).",
        {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Jira issue key (e.g., ENG-1234)"},
            },
            "required": ["issue_key"],
        },
    )
    async def jira_get_issue(args: dict[str, Any]) -> dict[str, Any]:
        if not _jira_api:
            return {"content": [{"type": "text", "text": "Jira not configured"}]}
        result = await _jira_api(
            f"/rest/api/3/issue/{args['issue_key']}",
            {"fields": "summary,status,priority,assignee,description,comment,updated,created"},
        )
        if "error" in result or "errorMessages" in result:
            return {"content": [{"type": "text", "text": f"Jira error: {result}"}]}
        f = result.get("fields", {})
        desc = f.get("description", {})
        # Extract text from Atlassian Document Format
        desc_text = ""
        if isinstance(desc, dict):
            for block in desc.get("content", []):
                for item in block.get("content", []):
                    if item.get("type") == "text":
                        desc_text += item.get("text", "")
                desc_text += "\n"
        return {"content": [{"type": "text", "text": str({
            "key": result["key"],
            "summary": f.get("summary", ""),
            "status": f.get("status", {}).get("name", ""),
            "priority": f.get("priority", {}).get("name", ""),
            "assignee": f.get("assignee", {}).get("displayName", "") if f.get("assignee") else "Unassigned",
            "description": desc_text[:500],
            "updated": f.get("updated", ""),
            "created": f.get("created", ""),
        })}]}

    all_tools = [
        slack_list_conversations, slack_get_history, slack_get_thread,
        slack_search_messages, slack_send_message, slack_get_user_info,
        jira_search, jira_get_issue,
        create_approval, send_notification, log_to_obsidian,
    ]
    return all_tools


def reset_server_cache():
    """Reset the cached server instance (useful for testing)."""
    global _cached_server, _cached_server_key
    _cached_server = None
    _cached_server_key = None
