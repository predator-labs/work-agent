import json as _json
import re

from claude_agent_sdk import query, ClaudeAgentOptions

from config.settings import Settings
from shared.state import StateManager
from shared.notifications import Notifier
from shared.skill_loader import SkillLoader
from shared.context_loader import ContextLoader
from shared.custom_tools import build_custom_tools_server
from prompts.slack_triage import build_prompt


class SlackTriage:
    SKILLS = ["send-slack-message-sugam"]

    def __init__(
        self,
        state: StateManager,
        notifier: Notifier,
        skills_path: str,
        repos_path: str,
        slack_user_id: str,
        jira_email: str,
        settings: Settings | None = None,
    ):
        self.state = state
        self.notifier = notifier
        self.skills_path = skills_path
        self.repos_path = repos_path
        self.slack_user_id = slack_user_id
        self.jira_email = jira_email
        self.settings = settings

    def build_mcp_servers(self) -> dict:
        servers = {}
        servers["agent-tools"] = build_custom_tools_server(
            self.state, self.notifier,
            slack_user_token=self.settings.slack_user_token if self.settings else "",
            slack_bot_token=self.settings.slack_bot_token if self.settings else "",
        )
        return servers

    async def run(self) -> dict:
        """Run Slack triage. Returns structured classification results."""
        skill_loader = SkillLoader(self.skills_path)
        context_loader = ContextLoader(self.repos_path)

        skills_content = skill_loader.load_many(self.SKILLS)
        context = context_loader.load_root()

        current_state = await self.state.read()
        last_read = current_state.get("slack", {}).get("last_read", {})

        prompt = build_prompt(
            slack_user_id=self.slack_user_id,
            context=context,
            skills=skills_content,
        )

        task_prompt = (
            f"Triage my Slack messages. Process in priority order: "
            f"DMs first, then @mentions, then AI/ML topics. "
            f"Max 50 channels per run. "
            f"Last-read timestamps: {last_read}\n\n"
            f"IMPORTANT: After triaging all messages, you MUST output your final summary as a single JSON object "
            f"(no markdown, no extra text — ONLY valid JSON) with these keys:\n"
            f'{{"simple": [...], "pr_reviews": [...], "issues": [...], "informational": [...]}}\n\n'
            f"Each simple item: {{\"channel\": \"...\", \"channel_id\": \"...\", \"thread_ts\": \"...\", \"from\": \"...\", \"summary\": \"...\", \"draft_reply\": \"...\"}}\n"
            f"Each pr_review item: {{\"url\": \"...\", \"requester\": \"...\", \"repo\": \"...\", \"slack_thread\": {{\"channel_id\": \"...\", \"thread_ts\": \"...\"}}}}\n"
            f"Each issue item: {{\"description\": \"...\", \"source_channel\": \"...\", \"priority\": \"high|medium|low\", \"tickets\": [...]}}\n"
            f"Each informational item: {{\"channel\": \"...\", \"summary\": \"...\"}}\n\n"
            f"Do NOT use the create_approval tool — just return the JSON summary."
        )

        results = {"simple": [], "pr_reviews": [], "issues": [], "informational": []}
        raw_output = ""

        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "mcp__agent-tools__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=50,
            ),
        ):
            if hasattr(message, "result"):
                raw_output = message.result

        # Parse the raw output into structured results
        parsed = _parse_triage_result(raw_output)
        if parsed:
            results.update(parsed)
        else:
            results["raw_result"] = raw_output

        # Create approvals for simple messages that need replies
        for item in results.get("simple", []):
            if item.get("draft_reply") and item.get("channel_id"):
                try:
                    await self.state.add_pending_approval(
                        task_id=f"slack-reply-{item.get('channel_id', 'unknown')}-{item.get('thread_ts', 'latest')}",
                        approval_type="slack_reply",
                        payload={
                            "channel_id": item["channel_id"],
                            "thread_ts": item.get("thread_ts"),
                            "text": item["draft_reply"],
                        },
                        context={"from": item.get("from", ""), "summary": item.get("summary", "")},
                    )
                    await self.notifier.push(
                        message=f"Reply to {item.get('from', 'someone')}: {item.get('summary', '')[:100]}",
                        title="Approve Slack Reply?",
                        priority="default",
                    )
                except Exception:
                    pass

        # Create approvals for PR reviews
        for item in results.get("pr_reviews", []):
            if item.get("url"):
                try:
                    await self.state.add_pending_approval(
                        task_id=f"pr-review-{item['url'].split('/')[-1]}",
                        approval_type="pr_review",
                        payload={"url": item["url"], "slack_thread": item.get("slack_thread", {})},
                        context={"requester": item.get("requester", ""), "repo": item.get("repo", "")},
                    )
                except Exception:
                    pass

        # Notify about issues
        issue_count = len(results.get("issues", []))
        pr_count = len(results.get("pr_reviews", []))
        simple_count = len(results.get("simple", []))
        if issue_count + pr_count + simple_count > 0:
            await self.notifier.push(
                message=f"{pr_count} PRs to review, {issue_count} issues, {simple_count} replies to approve",
                title="Slack Triage Complete",
                priority="high" if issue_count > 0 else "default",
            )

        return results


def _parse_triage_result(raw: str) -> dict | None:
    """Parse the agent's result into structured triage categories."""
    if not raw:
        return None

    # Try direct JSON parse
    try:
        data = _json.loads(raw.strip())
        if isinstance(data, dict):
            return _extract_categories(data)
    except (ValueError, _json.JSONDecodeError):
        pass

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        try:
            data = _json.loads(json_match.group(1))
            if isinstance(data, dict):
                return _extract_categories(data)
        except (ValueError, _json.JSONDecodeError):
            pass

    # Try to find JSON object anywhere in the text (last resort)
    # Look for the outermost { ... } that contains our keys
    brace_depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == '{':
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start is not None:
                candidate = raw[start:i + 1]
                try:
                    data = _json.loads(candidate)
                    if isinstance(data, dict) and any(k in data for k in ("simple", "pr_reviews", "issues")):
                        return _extract_categories(data)
                except (ValueError, _json.JSONDecodeError):
                    pass
                start = None

    return None


def _extract_categories(data: dict) -> dict:
    """Extract the four triage categories from a parsed dict."""
    result = {}
    for key in ("simple", "pr_reviews", "issues", "informational"):
        if key in data and isinstance(data[key], list):
            result[key] = data[key]
        else:
            result[key] = []
    return result
