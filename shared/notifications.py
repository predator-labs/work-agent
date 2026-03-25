import httpx


class Notifier:
    def __init__(self, ntfy_topic: str, slack_user_id: str, agent_url: str = "http://127.0.0.1:8000", agent_secret: str = ""):
        self.ntfy_topic = ntfy_topic
        self.slack_user_id = slack_user_id
        self.agent_url = agent_url
        self.agent_secret = agent_secret

    async def push(
        self,
        message: str,
        title: str = "Work Agent",
        priority: str = "default",
        tags: str = "",
        actions: list[dict] | None = None,
    ) -> None:
        """Send a push notification via ntfy.sh.

        actions: list of ntfy action dicts, e.g.:
            [{"action": "http", "label": "Approve", "url": "http://...", "method": "POST"}]
        """
        headers = {
            "Title": title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = tags
        if actions:
            # ntfy action format: action=http, label=Approve, url=http://...
            action_strs = []
            for a in actions:
                parts = [f"{k}={v}" for k, v in a.items()]
                action_strs.append(", ".join(parts))
            headers["Actions"] = "; ".join(action_strs)

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{self.ntfy_topic}",
                content=message.encode(),
                headers=headers,
            )

    async def push_approval(
        self,
        task_id: str,
        action_summary: str,
        details: str = "",
        priority: str = "high",
    ) -> None:
        """Send an approval notification with Approve/Reject action buttons."""
        message = f"{action_summary}\n\nTask: {task_id}"
        if details:
            message += f"\n{details[:200]}"

        await self.push(
            message=message,
            title="Approval Required",
            priority=priority,
            tags="warning",
            actions=[
                {
                    "action": "http",
                    "label": "Approve",
                    "url": f"{self.agent_url}/approve/{task_id}",
                    "method": "POST",
                    "headers": f"Authorization=Bearer {self.agent_secret}" if self.agent_secret else "",
                    "clear": "true",
                },
                {
                    "action": "http",
                    "label": "Reject",
                    "url": f"{self.agent_url}/reject/{task_id}",
                    "method": "POST",
                    "headers": f"Authorization=Bearer {self.agent_secret}" if self.agent_secret else "",
                    "clear": "true",
                },
            ],
        )

    async def push_with_reply(
        self,
        message: str,
        title: str = "Work Agent",
        task_id: str = "",
    ) -> None:
        """Send a notification that allows replying with feedback."""
        actions = []
        if task_id:
            actions = [
                {
                    "action": "http",
                    "label": "Approve",
                    "url": f"{self.agent_url}/approve/{task_id}",
                    "method": "POST",
                    "headers": f"Authorization=Bearer {self.agent_secret}" if self.agent_secret else "",
                    "clear": "true",
                },
                {
                    "action": "http",
                    "label": "Reject",
                    "url": f"{self.agent_url}/reject/{task_id}",
                    "method": "POST",
                    "headers": f"Authorization=Bearer {self.agent_secret}" if self.agent_secret else "",
                    "clear": "true",
                },
            ]

        await self.push(
            message=message,
            title=title,
            priority="default",
            actions=actions if actions else None,
        )

    def format_approval_message(self, task_id: str, action: str, details: str) -> str:
        return (
            f"*Approval Required*\n"
            f"*Action:* {action}\n"
            f"*Details:*\n{details}\n\n"
            f"*Task ID:* `{task_id}`\n"
            f"Approve: `work-agent approve {task_id}`\n"
            f"Reject: `work-agent reject {task_id}`"
        )
