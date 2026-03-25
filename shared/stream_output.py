"""Stream output renderer — shows agent progress like Claude Code / Cursor."""

import sys
import time
import random

from claude_agent_sdk import (
    StreamEvent, AssistantMessage, ResultMessage,
    SystemMessage, UserMessage, RateLimitEvent,
    TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock,
)

# Colors
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
WHITE = "\033[37m"

# Activity verbs for different tool types
TOOL_VERBS = {
    # Slack
    "slack_list_conversations": "Scanning Slack channels...",
    "slack_get_history": "Reading messages...",
    "slack_search_messages": "Searching Slack...",
    "slack_get_thread": "Reading thread...",
    "slack_send_message": "Sending message...",
    "slack_get_user_info": "Looking up user...",
    # Agent tools
    "create_approval": "Queuing approval...",
    "send_notification": "Sending notification...",
    "log_to_obsidian": "Logging to Obsidian...",
    # Bitbucket
    "getPullRequest": "Fetching PR details...",
    "getPullRequestDiff": "Reading diff...",
    "getPullRequestDiffStat": "Analyzing changed files...",
    "getPullRequestComments": "Reading review comments...",
    "getPullRequestCommits": "Checking commits...",
    "getPullRequestActivity": "Reading PR activity...",
    "addPullRequestComment": "Adding review comment...",
    "addPendingPullRequestComment": "Drafting comment...",
    "publishPendingComments": "Publishing review...",
    "approvePullRequest": "Approving PR...",
    "getPendingReviewPRs": "Finding PRs to review...",
    "listRepositories": "Listing repositories...",
    "getPipelineRun": "Checking pipeline...",
    "getPipelineStepLogs": "Reading build logs...",
    # Jira
    "searchJiraIssuesUsingJql": "Searching Jira...",
    "getJiraIssue": "Reading ticket...",
    "createJiraIssue": "Creating Jira ticket...",
    "editJiraIssue": "Updating ticket...",
    "transitionJiraIssue": "Moving ticket...",
    "addCommentToJiraIssue": "Adding comment...",
    "lookupJiraAccountId": "Looking up assignee...",
    # Confluence
    "searchConfluenceUsingCql": "Searching docs...",
    "getConfluencePage": "Reading documentation...",
    "createConfluencePage": "Creating page...",
    # Codacy
    "codacy_get_pull_request_git_diff": "Running code analysis...",
    "codacy_list_pull_request_issues": "Checking code quality...",
    # CircleCI
    "get_latest_pipeline_status": "Checking CI status...",
    "get_build_failure_logs": "Reading build failures...",
    "find_flaky_tests": "Finding flaky tests...",
    # File operations
    "Read": "Reading file...",
    "Write": "Writing file...",
    "Edit": "Editing file...",
    "Glob": "Finding files...",
    "Grep": "Searching code...",
    "Bash": "Running command...",
}

THINKING_VERBS = [
    "Deciphering...",
    "Analyzing...",
    "Processing...",
    "Reasoning...",
    "Evaluating...",
    "Considering...",
    "Investigating...",
    "Examining...",
    "Reflecting...",
    "Synthesizing...",
]

PR_REVIEW_VERBS = [
    "Reading diff...",
    "Checking for bugs...",
    "Analyzing code quality...",
    "Reviewing logic...",
    "Checking security...",
]


class StreamRenderer:
    """Renders streaming agent output to terminal."""

    def __init__(self, context: str = ""):
        self.context = context
        self._last_tool = ""
        self._tool_count = 0
        self._start_time = time.time()
        self._thinking_shown = False

    def _elapsed(self) -> str:
        elapsed = time.time() - self._start_time
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        return f"{elapsed / 60:.1f}m"

    def _print_status(self, icon: str, text: str, color: str = DIM):
        """Print a status line with timestamp."""
        sys.stdout.write(f"\r{color}{icon} {text}{RESET}\n")
        sys.stdout.flush()

    def _print_inline(self, text: str, color: str = DIM):
        """Print inline status (overwrites current line)."""
        # Clear line and print
        sys.stdout.write(f"\r\033[K{color}{text}{RESET}")
        sys.stdout.flush()

    def render(self, message):
        """Render a single streaming message."""
        if isinstance(message, StreamEvent):
            self._render_stream_event(message)
        elif isinstance(message, AssistantMessage):
            self._render_assistant(message)
        elif isinstance(message, ResultMessage):
            self._render_result(message)
        elif isinstance(message, RateLimitEvent):
            self._print_status("", "Rate limited, waiting...", YELLOW)
        # Skip UserMessage, SystemMessage

    def _render_stream_event(self, event: StreamEvent):
        """Render streaming partial updates."""
        data = event.event
        event_type = data.get("type", "")

        if event_type == "content_block_start":
            block = data.get("content_block", {})
            if block.get("type") == "thinking":
                verb = random.choice(THINKING_VERBS)
                self._print_inline(f"  {verb}", MAGENTA)
                self._thinking_shown = True
            elif block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
                verb = TOOL_VERBS.get(short_name, TOOL_VERBS.get(tool_name, f"Using {short_name}..."))
                self._tool_count += 1
                self._last_tool = short_name
                self._print_status(f"  [{self._elapsed()}]", verb, CYAN)

        elif event_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text.strip():
                    # Show first 120 chars of text output
                    preview = text.strip()[:120].replace("\n", " ")
                    self._print_inline(f"  {preview}", DIM)

    def _render_assistant(self, msg: AssistantMessage):
        """Render a complete assistant message."""
        if msg.error:
            self._print_status("  ERROR", str(msg.error), "\033[31m")
            return

        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                tool_name = block.name
                short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
                verb = TOOL_VERBS.get(short_name, TOOL_VERBS.get(tool_name, f"Using {short_name}..."))
                self._tool_count += 1
                self._print_status(f"  [{self._elapsed()}]", verb, CYAN)

                # Show tool input preview for interesting tools
                if short_name == "slack_search_messages" and hasattr(block, "input"):
                    query = block.input.get("query", "") if isinstance(block.input, dict) else ""
                    if query:
                        self._print_inline(f"    query: {query}", DIM)

            elif isinstance(block, TextBlock):
                text = block.text.strip()
                if text and len(text) > 10:
                    # Show meaningful text output (skip short fragments)
                    for line in text.split("\n")[:5]:
                        line = line.strip()
                        if line:
                            self._print_status("  ", line[:150], WHITE)

            elif isinstance(block, ThinkingBlock):
                if not self._thinking_shown:
                    verb = random.choice(THINKING_VERBS)
                    self._print_inline(f"  {verb}", MAGENTA)
                self._thinking_shown = False

    def _render_result(self, msg: ResultMessage):
        """Render the final result."""
        elapsed = self._elapsed()
        cost = f"${msg.total_cost_usd:.2f}" if msg.total_cost_usd else "?"
        self._print_status(
            "",
            f"Done ({elapsed}, {self._tool_count} tool calls, {msg.num_turns} turns, {cost})",
            GREEN,
        )


def create_renderer(context: str = "") -> StreamRenderer:
    """Create a new stream renderer."""
    return StreamRenderer(context=context)
