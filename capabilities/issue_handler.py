import uuid
from claude_agent_sdk import query, ClaudeAgentOptions

from config.mcp import build_mcp_servers
from config.settings import Settings
from shared.state import StateManager
from shared.notifications import Notifier
from shared.skill_loader import SkillLoader
from shared.context_loader import ContextLoader
from shared.custom_tools import build_custom_tools_server
from prompts.issue_handler import (
    build_phase1_prompt,
    build_phase2_prompt,
    build_phase3_prompt,
    build_phase4_prompt,
)


class IssueHandler:
    SKILLS_PHASE1 = ["starting-feature-work", "create-eng-jira-ticket", "sync-repos"]
    SKILLS_PHASE2 = ["plan-review"]
    SKILLS_PHASE3 = [
        "setup-git-worktree", "running-unit-tests", "creating-pull-request",
        "rollbar-automation", "flaky-test-automation",
    ]
    SKILLS_PHASE4 = ["send-slack-message-sugam", "creating-pull-request"]

    def __init__(
        self,
        state: StateManager,
        notifier: Notifier,
        skills_path: str,
        repos_path: str,
        memory_path: str,
        jira_email: str,
        settings: Settings | None = None,
    ):
        self.state = state
        self.notifier = notifier
        self.skills_path = skills_path
        self.repos_path = repos_path
        self.memory_path = memory_path
        self.jira_email = jira_email
        self.settings = settings

    def build_mcp_servers(self) -> dict:
        servers = {}
        if self.settings:
            servers = build_mcp_servers(self.settings)
        servers["agent-tools"] = build_custom_tools_server(self.state, self.notifier)
        return servers

    async def create_issue(self, description: str, source: dict) -> str:
        """Create an issue entry in state. Returns issue_id."""
        issue_id = str(uuid.uuid4())
        await self.state.save_issue(issue_id, {
            "status": "investigating",
            "description": description,
            "source": source,
            "investigation": None,
            "jira_key": None,
            "plan": None,
            "branch": None,
            "pr_url": None,
        })
        return issue_id

    async def run_phase1(self, issue_id: str) -> dict:
        """Phase 1: Investigate + create Jira ticket."""
        issue = await self.state.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue not found: {issue_id}")

        skill_loader = SkillLoader(self.skills_path)
        context_loader = ContextLoader(self.repos_path)

        skills = skill_loader.load_many(self.SKILLS_PHASE1)
        context = context_loader.load_root()

        prompt = build_phase1_prompt(
            issue_description=issue["description"],
            source_context=str(issue.get("source", {})),
            context=context,
            skills=skills,
            jira_email=self.jira_email,
        )

        task_prompt = (
            f"Investigate this issue and prepare a Jira ticket.\n"
            f"First, sync the relevant repo to latest master.\n"
            f"Description: {issue['description']}\n"
            f"Use create_approval with type jira_ticket when ready."
        )

        result = {}
        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "Read", "Glob", "Grep", "Bash",
                    "mcp__agent-tools__*",
                    "mcp__atlassian__*",
                    "mcp__rollbar-server__*",
                    "mcp__rollbar-mlai__*",
                    "mcp__deductive__*",
                    "mcp__dbhub__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=50,
                cwd=self.repos_path,
            ),
        ):
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        await self.state.save_issue(issue_id, {**issue, "status": "awaiting_jira_approval"})
        return result

    async def run_phase2(self, issue_id: str) -> dict:
        """Phase 2: Brainstorm + Plan."""
        issue = await self.state.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue not found: {issue_id}")

        skill_loader = SkillLoader(self.skills_path)
        context_loader = ContextLoader(self.repos_path)

        service = issue.get("investigation", {}).get("service", "") if issue.get("investigation") else ""
        skills = skill_loader.load_many(self.SKILLS_PHASE2)
        context = context_loader.build_context(service=service, memory_path=self.memory_path)

        prompt = build_phase2_prompt(
            investigation=str(issue.get("investigation", "No investigation data")),
            jira_key=issue.get("jira_key", "TBD"),
            context=context,
            skills=skills,
        )

        task_prompt = (
            f"Brainstorm and create an implementation plan for {issue.get('jira_key', 'this issue')}.\n"
            f"Use create_approval with type plan_approval when ready."
        )

        result = {}
        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "Read", "Glob", "Grep",
                    "mcp__agent-tools__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=30,
                cwd=self.repos_path,
            ),
        ):
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        await self.state.save_issue(issue_id, {**issue, "status": "awaiting_plan_approval"})
        return result

    async def run_phase3(self, issue_id: str) -> dict:
        """Phase 3: Implement + Test + Verify."""
        issue = await self.state.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue not found: {issue_id}")

        skill_loader = SkillLoader(self.skills_path)
        context_loader = ContextLoader(self.repos_path)

        service = issue.get("investigation", {}).get("service", "") if issue.get("investigation") else ""
        skills = skill_loader.load_many(self.SKILLS_PHASE3)
        context = context_loader.build_context(service=service, memory_path=self.memory_path)
        memory = context_loader.load_memory(self.memory_path)

        prompt = build_phase3_prompt(
            plan=str(issue.get("plan", "No plan data")),
            jira_key=issue.get("jira_key", "TBD"),
            context=context,
            skills=skills,
            memory=memory,
        )

        task_prompt = (
            f"Implement the approved plan for {issue.get('jira_key', 'this issue')}.\n"
            f"Create branch, implement, write tests, verify.\n"
            f"Use create_approval with type pr_creation when ready."
        )

        result = {}
        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "Read", "Write", "Edit", "Glob", "Grep", "Bash",
                    "mcp__agent-tools__*",
                    "mcp__bitbucket__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=100,
                cwd=self.repos_path,
            ),
        ):
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        await self.state.save_issue(issue_id, {**issue, "status": "awaiting_pr_approval"})
        return result

    async def run_phase4(self, issue_id: str) -> dict:
        """Phase 4: Create PR + Notify."""
        issue = await self.state.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue not found: {issue_id}")

        skill_loader = SkillLoader(self.skills_path)
        skills = skill_loader.load_many(self.SKILLS_PHASE4)

        prompt = build_phase4_prompt(
            pr_details=str(issue.get("pr_details", {})),
            jira_key=issue.get("jira_key", "TBD"),
            skills=skills,
        )

        task_prompt = (
            f"Create a Bitbucket PR for {issue.get('jira_key', 'this issue')} and "
            f"notify Sangram in #ai-ml channel for review."
        )

        result = {}
        async for message in query(
            prompt=task_prompt,
            options=ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
                mcp_servers=self.build_mcp_servers(),
                allowed_tools=[
                    "Bash",
                    "mcp__agent-tools__*",
                    "mcp__bitbucket__*",
                ],
                permission_mode="bypassPermissions",
                max_turns=20,
                cwd=self.repos_path,
            ),
        ):
            if hasattr(message, "result"):
                result["raw_result"] = message.result

        await self.state.save_issue(issue_id, {**issue, "status": "complete"})
        return result
