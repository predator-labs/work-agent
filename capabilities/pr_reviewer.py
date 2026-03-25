import re
from claude_agent_sdk import query, ClaudeAgentOptions

from config.mcp import build_mcp_servers
from config.settings import Settings
from shared.state import StateManager
from shared.notifications import Notifier
from shared.skill_loader import SkillLoader
from shared.context_loader import ContextLoader
from shared.custom_tools import build_custom_tools_server
from prompts.pr_reviewer import build_prompt


class PRReviewer:
    SKILLS = ["sugam-code-review", "docyt-review-pr", "docyt-conventions"]

    def __init__(
        self,
        state: StateManager,
        notifier: Notifier,
        skills_path: str,
        repos_path: str,
        memory_path: str,
        settings: Settings | None = None,
    ):
        self.state = state
        self.notifier = notifier
        self.skills_path = skills_path
        self.repos_path = repos_path
        self.memory_path = memory_path
        self.settings = settings

    def parse_pr_url(self, url: str) -> tuple[str, str]:
        """Extract repo slug and PR number from Bitbucket URL."""
        match = re.search(r"bitbucket\.org/[^/]+/([^/]+)/pull-requests/(\d+)", url)
        if not match:
            raise ValueError(f"Not a valid Bitbucket PR URL: {url}")
        return match.group(1), match.group(2)

    def build_mcp_servers(self) -> dict:
        servers = {}
        if self.settings:
            servers = build_mcp_servers(self.settings)
        servers["agent-tools"] = build_custom_tools_server(
            self.state, self.notifier,
            slack_user_token=self.settings.slack_user_token if self.settings else "",
            slack_bot_token=self.settings.slack_bot_token if self.settings else "",
        )
        return servers

    async def run(
        self,
        pr_url: str,
        slack_thread: dict | None = None,
    ) -> dict:
        """Review a PR. Returns review results."""
        repo, pr_num = self.parse_pr_url(pr_url)
        pr_id = f"{repo}/{pr_num}"

        skill_loader = SkillLoader(self.skills_path)
        context_loader = ContextLoader(self.repos_path)

        # Detect service from repo name
        service = repo.replace("-", "_") if "_" in repo or "-" in repo else repo

        skills_content = skill_loader.load_many(self.SKILLS)
        context = context_loader.build_context(service=service, memory_path=self.memory_path)
        memory = context_loader.load_memory(self.memory_path)

        # Check for previous review
        previous_review = await self.state.get_pr_review(pr_id)
        re_review_context = ""
        if previous_review:
            re_review_context = (
                f"\n## Previous Review\n"
                f"This PR was previously reviewed on {previous_review['reviewed_at']}.\n"
                f"Decision: {previous_review['decision']}\n"
                f"Issues raised:\n"
            )
            for issue in previous_review.get("issues_raised", []):
                re_review_context += f"- [{issue['severity']}] {issue['file']}:{issue.get('line', '?')} — {issue['description']}\n"
            re_review_context += "\nCheck if these issues have been resolved in the current diff.\n"

        prompt = build_prompt(context=context, skills=skills_content, memory=memory)

        task_prompt = (
            f"Review Bitbucket PR: {pr_url}\n"
            f"Repository: {repo}, PR #{pr_num}\n"
            f"{re_review_context}\n"
            f"Steps:\n"
            f"1. Fetch the PR diff and details using Bitbucket MCP\n"
            f"2. Analyze for critical issues ONLY\n"
            f"3. Either approve (no comments) or request changes (with inline comments)\n"
            f"4. Log the review to Obsidian\n"
            f"5. Send notification with the result\n"
        )

        if slack_thread:
            task_prompt += (
                f"\nAfter reviewing, reply in Slack thread {slack_thread.get('thread_ts')} "
                f"in channel {slack_thread.get('channel')}, tagging the requester.\n"
            )

        result = {}

        from shared.stream_output import create_renderer
        renderer = create_renderer(f"PR Review #{pr_num}")

        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "mcp__agent-tools__*",
                    "mcp__bitbucket__*",
                    "mcp__codacy__*",
                    "mcp__circleci__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=30,
            ),
        ):
            renderer.render(message)
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        return result
