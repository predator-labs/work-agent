from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions

from config.settings import Settings
from shared.state import StateManager
from shared.notifications import Notifier
from shared.skill_loader import SkillLoader
from shared.custom_tools import build_custom_tools_server
from prompts.daily_planner import build_plan_day_prompt, build_end_day_prompt


class DailyPlanner:
    PLAN_SKILLS = [
        "es-churn-sensitive-status",
        "es-high-priority-sla-breach-report",
        "fetch-p0-feature-requests",
    ]
    END_DAY_SKILLS = [
        "docyt-release-notes",
    ]

    def __init__(
        self,
        state: StateManager,
        notifier: Notifier,
        skills_path: str,
        repos_path: str,
        vault_path: str,
        jira_email: str,
        settings: Settings | None = None,
    ):
        self.state = state
        self.notifier = notifier
        self.skills_path = skills_path
        self.repos_path = repos_path
        self.vault_path = vault_path
        self.jira_email = jira_email
        self.settings = settings

    def today_log_path(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return Path(self.vault_path) / "daily-logs" / f"{today}.md"

    def build_mcp_servers(self, include_external: bool = False) -> dict:
        # Only start heavy MCP servers when explicitly needed
        servers = {}
        if include_external and self.settings:
            from config.mcp import build_mcp_servers as _build
            servers = _build(self.settings)
        servers["agent-tools"] = build_custom_tools_server(
            self.state, self.notifier,
            slack_user_token=self.settings.slack_user_token if self.settings else "",
            slack_bot_token=self.settings.slack_bot_token if self.settings else "",
        )
        return servers

    async def plan_day(self, slack_results: str = "") -> dict:
        """Morning planning: summarize Slack results, send DM + notification."""
        skill_loader = SkillLoader(self.skills_path)
        skills = skill_loader.load_many(self.PLAN_SKILLS)

        prompt = build_plan_day_prompt(
            jira_email=self.jira_email,
            slack_results=slack_results,
            skills=skills,
        )

        task_prompt = (
            "Create my daily plan based on the Slack triage results provided in the system prompt.\n"
            "Steps:\n"
            "1. Summarize the Slack triage results into prioritized action items (P1-P4)\n"
            "2. Send me a Slack DM with the daily plan summary\n"
            "3. Send an ntfy notification: 'Daily plan ready'\n"
            "4. Log the plan to Obsidian\n"
            "Do NOT attempt to query Jira or Bitbucket directly — use the Slack results provided."
        )

        result = {}
        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "mcp__agent-tools__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=15,
            ),
        ):
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        return result

    async def end_day(self) -> dict:
        """End-of-day summary."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        skill_loader = SkillLoader(self.skills_path)
        skills = skill_loader.load_many(self.END_DAY_SKILLS)

        prompt = build_end_day_prompt(
            vault_path=self.vault_path,
            today=today,
            skills=skills,
        )

        task_prompt = (
            f"Generate my end-of-day summary:\n"
            f"1. Read today's log at {self.vault_path}/daily-logs/{today}.md\n"
            f"2. Summarize accomplishments\n"
            f"3. Note incomplete items for tomorrow\n"
            f"4. Write summary to Obsidian\n"
            f"5. Send Slack DM recap"
        )

        result = {}
        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "Read",
                    "mcp__agent-tools__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=20,
            ),
        ):
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        return result
