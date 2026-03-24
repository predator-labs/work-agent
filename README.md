# work-agent

Personal autonomous agent that handles engineering workflows — Slack triage, PR review, issue handling, and daily planning.

Built with Claude Agent SDK (Python), FastAPI, and Typer. Runs in Docker.

## What it does

- **Slack Triage** — Reads DMs, @mentions, and AI/ML topics. Auto-replies to simple messages (with approval). Routes PR reviews and issues to dedicated handlers.
- **PR Review** — Critical-only code review on Bitbucket PRs. No nitpicking. Approves clean PRs silently. Re-reviews detect resolved issues.
- **Issue/Feature Handler** — Investigates bugs (RCA) or features, creates Jira tickets, brainstorms, plans, implements, tests, and creates PRs. 4-phase workflow with approval gates.
- **Daily Planner** — Morning planning via Todoist (prioritized tasks from Jira + Slack + Bitbucket). Activity logging in Obsidian. End-of-day summaries.
- **Push Notifications** — ntfy.sh for urgent alerts and approval requests on your phone.
- **Background Dispatch** — Long tasks run in background with `--bg` flag. macOS sleep prevention via `caffeinate`.

## One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/predator-labs/work-agent/main/install.sh | bash
```

This will:
1. Check prerequisites (Python 3.12+, Node.js 18+, git)
2. Install Claude Code CLI if missing
3. Clone the repo to `~/work-agent`
4. Create virtual environment and install dependencies
5. Create `.env` from template
6. Add `work-agent` to your PATH
7. Run tests to verify

After install, edit your credentials and start:
```bash
nano ~/work-agent/.env          # Add your API keys
source ~/.zshrc                  # Reload shell
work-agent                       # Start the server
```

Custom install location:
```bash
WORK_AGENT_DIR=/path/to/install curl -fsSL https://raw.githubusercontent.com/predator-labs/work-agent/main/install.sh | bash
```

## Setup on a New Device

### Prerequisites

| Requirement | Version | Install |
|-------------|---------|---------|
| Python | 3.12+ | `pyenv install 3.12` or [python.org](https://python.org) |
| Node.js | 18+ | `brew install node` or [nodejs.org](https://nodejs.org) |
| Git | any | `brew install git` or [git-scm.com](https://git-scm.com) |
| Claude Code CLI | latest | `npm install -g @anthropic-ai/claude-code` |
| Docker | optional | [docker.com](https://docker.com) (for containerized deployment) |

### Manual Setup (step by step)

```bash
# 1. Clone
git clone https://github.com/predator-labs/work-agent.git
cd work-agent

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
nano .env    # Fill in your API keys (see Configuration section below)

# 5. Add to PATH (one-time)
echo 'export PATH="'$(pwd)'/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 6. Authenticate Claude Code CLI (first time only)
claude     # Opens browser for OAuth login, then Ctrl+C

# 7. Run tests
python -m pytest tests/ -v

# 8. Start
work-agent
```

### What you need from each service

| Service | What to get | Where |
|---------|------------|-------|
| **Slack** | Bot/User OAuth Token + Team ID | [api.slack.com/apps](https://api.slack.com/apps) (see Slack App Setup below) |
| **Slack** | Your Member ID | Slack profile → ... → Copy member ID |
| **Bitbucket** | App password | Bitbucket → Personal Settings → App passwords |
| **Jira** | API token | [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |
| **CircleCI** | Personal API token | CircleCI → User Settings → Personal API Tokens |
| **Codacy** | Account API token | Codacy → Your Account → API tokens |
| **Rollbar** | Project access token | Rollbar → Project → Settings → Project Access Tokens |
| **Todoist** | API token | Todoist → Settings → Integrations → Developer |
| **ntfy** | Install app on phone | [ntfy.sh](https://ntfy.sh) → subscribe to topic `work-agent` |

### Global `work-agent` Command

After cloning and setting up, add the CLI to your PATH:

```bash
# Add to your shell profile (one-time setup)
echo 'export PATH="/path/to/work-agent/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Now use `work-agent` from any terminal:

```bash
# Start the server (no args)
work-agent

# Run specific tasks
work-agent slack                                    # Triage Slack messages
work-agent review-pr <bitbucket-pr-url>            # Review a PR
work-agent handle "fix the login bug"              # Handle an issue
work-agent plan-day                                 # Morning planning
work-agent end-day                                  # End-of-day summary
work-agent run-all                                  # Full cycle: Slack + PRs + plan
work-agent status                                   # Show pending approvals
work-agent approve <task-id>                        # Approve an action
work-agent reject <task-id>                         # Reject an action

# Background dispatch (returns immediately)
work-agent run-all --bg
work-agent handle "add caching" --bg

# Start the API server explicitly
work-agent serve
```

### Run from a Fresh Terminal (without global install)

```bash
cd /path/to/work-agent && source .venv/bin/activate && uvicorn server:app --host 127.0.0.1 --port 8000
```

To run in background:
```bash
cd /path/to/work-agent && source .venv/bin/activate && uvicorn server:app --host 127.0.0.1 --port 8000 &
```

### Docker Setup

```bash
# Build and run
docker compose build
docker compose up -d

# Check health
curl http://localhost:8000/health

# View logs
docker compose logs -f
```

## Configuration

Copy `.env.example` to `.env` and fill in:

### Required

| Variable | Description | Where to get it |
|----------|-------------|-----------------|
| `AGENT_SECRET` | Shared secret for API auth | Generate any random string |
| `SLACK_BOT_TOKEN` | Slack bot token (`xoxb-...`) | [api.slack.com/apps](https://api.slack.com/apps) - Your App - OAuth |
| `SLACK_TEAM_ID` | Slack workspace ID (`T...`) | Slack URL: `app.slack.com/client/T.../...` |
| `SLACK_USER_ID` | Your Slack member ID | Slack profile - three dots - Copy member ID |

### Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) - Create New App - From scratch
2. Name: `Work Agent`, select your workspace
3. Go to **OAuth & Permissions** - Add Bot Token Scopes:
   - `channels:history`, `channels:read`, `groups:history`, `groups:read`
   - `im:history`, `im:read`, `mpim:history`, `mpim:read`
   - `chat:write`, `users:read`, `reactions:read`, `reactions:write`
   - `usergroups:read`
   - `files:read`, `files:write` (optional, for file handling)
   - `pins:read`, `bookmarks:read` (optional)
4. Click **Install to Workspace** - Authorize
5. Copy the **Bot User OAuth Token** (`xoxb-...`) to `SLACK_BOT_TOKEN`

### Using a User Token (for full channel access)

A bot token only sees channels it's invited to. A **user token** (`xoxp-...`) inherits all your channel memberships and DM access automatically.

To get a user token:
1. Go to [api.slack.com/apps](https://api.slack.com/apps) - select your Work Agent app
2. Go to **OAuth & Permissions**
3. Under **User Token Scopes**, add the same scopes as bot scopes above plus `search:read`
4. Click **Reinstall to Workspace** - Authorize
5. Copy the **User OAuth Token** (`xoxp-...`)
6. Set `SLACK_BOT_TOKEN=xoxp-...` in your `.env` (the MCP server accepts both token types)

### Optional Integrations

| Variable | Description |
|----------|-------------|
| `BITBUCKET_USERNAME` / `BITBUCKET_PASSWORD` | Bitbucket app password for PR operations |
| `JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN` | Jira for ticket management |
| `CIRCLECI_TOKEN` | CircleCI for pipeline status |
| `CODACY_ACCOUNT_TOKEN` | Codacy for code quality |
| `ROLLBAR_TOKEN_DOCYT_SERVER` | Rollbar error tracking (server) |
| `ROLLBAR_TOKEN_DOCYT_MLAI` | Rollbar error tracking (ML/AI) |
| `TODOIST_API_KEY` | Todoist for daily task management |
| `NTFY_TOPIC` | ntfy.sh topic for push notifications |

### Paths (Docker defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSIDIAN_VAULT_PATH` | `/vault` | Obsidian vault for daily logs |
| `REPOS_PATH` | `/repos` | Monorepo root |
| `SKILLS_PATH` | `/repos/docyt_ops/ai/skills` | Skill definitions |
| `MEMORY_PATH` | `/repos/.claude/projects/.../memory` | User preferences |

## Usage

### API

All endpoints require `Authorization: Bearer <AGENT_SECRET>` header.

```bash
# Health check (no auth needed)
curl http://localhost:8000/health

# Full cycle
curl -X POST -H "Authorization: Bearer $SECRET" http://localhost:8000/run/all

# Slack triage
curl -X POST -H "Authorization: Bearer $SECRET" http://localhost:8000/run/slack

# Review a PR
curl -X POST -H "Authorization: Bearer $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"pr_url":"https://bitbucket.org/kmnss/repo/pull-requests/123"}' \
  http://localhost:8000/run/review-pr

# Handle an issue (background)
curl -X POST -H "Authorization: Bearer $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"description":"fix auth timeout","background":true}' \
  http://localhost:8000/run/handle

# Check status
curl -H "Authorization: Bearer $SECRET" http://localhost:8000/status

# Approve/reject
curl -X POST -H "Authorization: Bearer $SECRET" http://localhost:8000/approve/<task-id>
curl -X POST -H "Authorization: Bearer $SECRET" http://localhost:8000/reject/<task-id>
```

## Architecture

```
CLI (Typer)  --+
               +--> capabilities/ --> Claude Agent SDK + MCP Servers
API (FastAPI)--+
```

### MCP Servers

| Server | Purpose |
|--------|---------|
| Slack | Read/write messages, channels, DMs |
| Bitbucket | PR operations (diff, comment, approve) |
| Atlassian | Jira tickets, Confluence docs |
| CircleCI | Pipeline status, test results |
| Codacy | Code quality analysis |
| Rollbar (x2) | Production error tracking |
| DBHub | Database schema inspection |
| Deductive | Infrastructure monitoring |
| Todoist | Task management |
| Figma | Design file access |

### Approval Workflow

Long-running actions use a two-phase pattern:
1. **Phase 1**: Agent prepares the action, saves to state, sends Slack DM + ntfy push
2. **Phase 2**: You approve via `agent approve <id>` or `POST /approve/<id>`, agent executes

### Issue Handler Phases

```
Phase 0: Sync repos to latest
Phase 1: Investigate + Create Jira  --> [APPROVAL]
Phase 2: Brainstorm + Plan         --> [APPROVAL]
Phase 3: Implement + Test          --> [APPROVAL]
Phase 4: Create PR + Notify team
```

## Mobile Access

- **Slack** — DMs with summaries, draft approvals, PR review results
- **Todoist** — Daily tasks appear automatically
- **ntfy.sh** — Push notifications for urgent items and approval requests
  - Install the ntfy app (iOS / Android)
  - Subscribe to your topic (default: `work-agent`)

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Lint
ruff check .
ruff format --check .

# Add a new capability
# 1. Create capabilities/my_capability.py
# 2. Create prompts/my_capability.py
# 3. Wire into server.py and agent.py
# 4. Add tests
```
