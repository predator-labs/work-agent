from claude_agent_sdk import query, ClaudeAgentOptions

from config.mcp import build_mcp_servers
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
        # Slack triage only needs agent-tools (which includes Slack API tools)
        # No need to start bitbucket, circleci, codacy, rollbar etc.
        servers = {}
        servers["agent-tools"] = build_custom_tools_server(
            self.state, self.notifier,
            slack_user_token=self.settings.slack_user_token if self.settings else "",
            slack_bot_token=self.settings.slack_bot_token if self.settings else "",
        )
        return servers

    async def run(self) -> dict:
        """Run Slack triage. Returns classification results."""
        skill_loader = SkillLoader(self.skills_path)
        context_loader = ContextLoader(self.repos_path)

        skills_content = skill_loader.load_many(self.SKILLS)
        context = context_loader.load_root()

        # Get last-read timestamps
        current_state = await self.state.read()
        last_read = current_state.get("slack", {}).get("last_read", {})

        prompt = build_prompt(
            slack_user_id=self.slack_user_id,
            context=context,
            skills=skills_content,
        )

        task_prompt = (
            f"Triage my Slack messages. Process channels in priority order: "
            f"DMs first, then @mentions, then AI/ML topics. "
            f"Max 50 channels per run. "
            f"Last-read timestamps: {last_read}\n"
            f"For each message that needs a reply, use create_approval tool. "
            f"For PR reviews, report the PR URL. "
            f"For issues/features, report the description. "
            f"Return a JSON summary of what was processed."
        )

        results = {"simple": [], "pr_reviews": [], "issues": [], "informational": []}

        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "mcp__agent-tools__*",
                    "mcp__bitbucket__*",
                    "mcp__atlassian__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=50,
            ),
        ):
            if hasattr(message, "result"):
                # Parse results from agent output
                results["raw_result"] = message.result

        return results
