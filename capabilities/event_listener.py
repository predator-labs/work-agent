"""Event-driven listener for Slack (Socket Mode) and Jira (polling)."""

import asyncio
import logging
import time

from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from config.settings import Settings
from shared.state import StateManager
from shared.notifications import Notifier

logger = logging.getLogger("work-agent.events")


class EventListener:
    """Listens for Slack events via Socket Mode and Jira changes via polling."""

    # Debounce: ignore duplicate events within this window (seconds)
    DEBOUNCE_SECONDS = 5
    # Jira poll interval
    JIRA_POLL_INTERVAL = 300  # 5 minutes
    # Full triage interval
    FULL_TRIAGE_INTERVAL = 1800  # 30 minutes

    def __init__(
        self,
        settings: Settings,
        state: StateManager,
        notifier: Notifier,
        on_mention: callable,
        on_dm: callable,
        on_pr_link: callable,
        on_full_triage: callable,
    ):
        self.settings = settings
        self.state = state
        self.notifier = notifier
        self.on_mention = on_mention
        self.on_dm = on_dm
        self.on_pr_link = on_pr_link
        self.on_full_triage = on_full_triage
        self._seen_events: dict[str, float] = {}
        self._running = False
        self._socket_client: SocketModeClient | None = None

    def _is_duplicate(self, event_id: str) -> bool:
        """Check if we've seen this event recently."""
        now = time.time()
        # Clean old entries
        self._seen_events = {k: v for k, v in self._seen_events.items() if now - v < self.DEBOUNCE_SECONDS * 10}
        if event_id in self._seen_events and now - self._seen_events[event_id] < self.DEBOUNCE_SECONDS:
            return True
        self._seen_events[event_id] = now
        return False

    def _is_relevant_message(self, event: dict) -> str | None:
        """Check if a message event is relevant. Returns category or None."""
        text = event.get("text", "")
        user = event.get("user", "")
        channel_type = event.get("channel_type", "")

        # Skip bot messages and our own messages
        if event.get("bot_id") or user == self.settings.slack_user_id:
            return None
        # Skip message edits/deletes
        if event.get("subtype") in ("message_changed", "message_deleted"):
            return None

        # DM
        if channel_type == "im":
            return "dm"

        # Direct @mention
        if f"<@{self.settings.slack_user_id}>" in text:
            return "mention"

        # @ai-ml-engineers group mention
        if "@ai-ml-engineers" in text.lower() or "ai-ml" in text.lower():
            return "mention"

        # PR link
        if "bitbucket.org" in text and "pull-requests" in text:
            return "pr_link"

        return None

    async def _handle_slack_event(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming Slack Socket Mode events."""
        # Always acknowledge immediately
        await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        if req.type != "events_api":
            return

        event = req.payload.get("event", {})
        event_type = event.get("type", "")
        # Use channel+ts as dedup key (more reliable than event_id for duplicate deliveries)
        event_id = f"{event.get('channel', '')}:{event.get('ts', '')}:{event.get('user', '')}"

        if self._is_duplicate(event_id):
            return

        if event_type not in ("message", "app_mention"):
            return

        category = self._is_relevant_message(event)
        if not category:
            return

        logger.info(f"Slack event: {category} from {event.get('user', '?')} in {event.get('channel', '?')}")

        try:
            if category == "dm":
                await self.on_dm(event)
            elif category == "mention":
                await self.on_mention(event)
            elif category == "pr_link":
                await self.on_pr_link(event)
        except Exception as e:
            logger.error(f"Error handling {category} event: {e}")

    async def _start_slack_socket(self):
        """Connect to Slack via Socket Mode."""
        if not self.settings.slack_app_token:
            logger.warning("No SLACK_APP_TOKEN — Slack Socket Mode disabled")
            return

        self._socket_client = SocketModeClient(
            app_token=self.settings.slack_app_token,
            web_client=None,  # We use our own HTTP calls
        )
        self._socket_client.socket_mode_request_listeners.append(self._handle_slack_event)

        logger.info("Connecting to Slack Socket Mode...")
        await self._socket_client.connect()
        logger.info("Slack Socket Mode connected")

    async def _jira_poll_loop(self):
        """Poll Jira for new assignments/updates."""
        while self._running:
            try:
                await self._check_jira_updates()
            except Exception as e:
                logger.error(f"Jira poll error: {e}")
            await asyncio.sleep(self.JIRA_POLL_INTERVAL)

    async def _check_jira_updates(self):
        """Check Jira for new tickets assigned to us."""
        import httpx

        if not self.settings.jira_url or not self.settings.jira_api_token:
            return

        # Get recently updated tickets assigned to us
        jql = f'assignee = "{self.settings.jira_email}" AND updated >= -5m ORDER BY updated DESC'
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.settings.jira_url}/rest/api/3/search",
                params={"jql": jql, "maxResults": 10, "fields": "summary,status,priority,updated"},
                auth=(self.settings.jira_username, self.settings.jira_api_token),
                timeout=30,
            )
            if resp.status_code != 200:
                return

            data = resp.json()
            issues = data.get("issues", [])
            if issues:
                for issue in issues:
                    key = issue["key"]
                    summary = issue["fields"]["summary"]
                    status = issue["fields"]["status"]["name"]
                    logger.info(f"Jira update: {key} — {summary} [{status}]")
                    await self.notifier.push(
                        message=f"{key}: {summary} [{status}]",
                        title="Jira Update",
                        priority="default",
                    )

    async def _full_triage_loop(self):
        """Run a full triage periodically as a fallback."""
        # Wait before first full triage — let events handle the initial burst
        await asyncio.sleep(self.FULL_TRIAGE_INTERVAL)
        while self._running:
            try:
                logger.info("Running scheduled full triage...")
                await self.on_full_triage()
            except Exception as e:
                logger.error(f"Full triage error: {e}")
            await asyncio.sleep(self.FULL_TRIAGE_INTERVAL)

    async def start(self):
        """Start all event listeners."""
        self._running = True
        logger.info("Starting event listeners...")

        tasks = []

        # Slack Socket Mode
        try:
            await self._start_slack_socket()
            logger.info("Slack Socket Mode: active")
        except Exception as e:
            logger.error(f"Slack Socket Mode failed: {e}")

        # Jira polling
        tasks.append(asyncio.create_task(self._jira_poll_loop()))
        logger.info("Jira polling: active (every 5m)")

        # Full triage fallback
        tasks.append(asyncio.create_task(self._full_triage_loop()))
        logger.info(f"Full triage fallback: active (every {self.FULL_TRIAGE_INTERVAL // 60}m)")

        await self.notifier.push(
            message="Event listeners started: Slack (real-time), Jira (5m poll), Full triage (30m)",
            title="Work Agent Online",
            priority="default",
        )

        # Keep running until stopped
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            for t in tasks:
                t.cancel()

    async def stop(self):
        """Stop all event listeners."""
        self._running = False
        if self._socket_client:
            await self._socket_client.disconnect()
            logger.info("Slack Socket Mode disconnected")
        logger.info("Event listeners stopped")
