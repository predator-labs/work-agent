import httpx


class Notifier:
    def __init__(self, ntfy_topic: str, slack_user_id: str):
        self.ntfy_topic = ntfy_topic
        self.slack_user_id = slack_user_id

    async def push(self, message: str, title: str = "Divyanshu Agent", priority: str = "default", tags: str = "") -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{self.ntfy_topic}",
                content=message.encode(),
                headers={"Title": title, "Priority": priority, "Tags": tags},
            )

    def format_approval_message(self, task_id: str, action: str, details: str) -> str:
        return (
            f"*Approval Required*\n"
            f"*Action:* {action}\n"
            f"*Details:*\n{details}\n\n"
            f"*Task ID:* `{task_id}`\n"
            f"Approve: `POST /approve/{task_id}` or `agent approve {task_id}`\n"
            f"Reject: `POST /reject/{task_id}` or `agent reject {task_id}`"
        )
