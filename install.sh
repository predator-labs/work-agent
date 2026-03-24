#!/usr/bin/env bash
set -e

# work-agent installer
# Usage: curl -fsSL https://raw.githubusercontent.com/predator-labs/work-agent/main/install.sh | bash

REPO="https://github.com/predator-labs/work-agent.git"
INSTALL_DIR="${WORK_AGENT_DIR:-$HOME/work-agent}"
SHELL_PROFILE=""

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         work-agent installer         ║"
echo "  ║    Predator Labs - predator-labs     ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Detect shell profile
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ]; then
    SHELL_PROFILE="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "/bin/bash" ]; then
    SHELL_PROFILE="$HOME/.bashrc"
else
    SHELL_PROFILE="$HOME/.profile"
fi

# Check prerequisites
echo "[1/7] Checking prerequisites..."

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo "  ✗ $1 not found. $2"
        return 1
    else
        echo "  ✓ $1 found ($(command -v "$1"))"
        return 0
    fi
}

MISSING=0
check_cmd "git" "Install: https://git-scm.com" || MISSING=1
check_cmd "python3" "Install Python 3.12+: https://python.org" || MISSING=1
check_cmd "node" "Install Node.js 18+: https://nodejs.org" || MISSING=1
check_cmd "npm" "Comes with Node.js" || MISSING=1

if [ $MISSING -eq 1 ]; then
    echo ""
    echo "Please install missing prerequisites and re-run."
    exit 1
fi

# Check Python version
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]); then
    echo "  ✗ Python $PY_VERSION found, but 3.12+ is required"
    echo "    Install via: pyenv install 3.12 && pyenv global 3.12"
    exit 1
fi
echo "  ✓ Python $PY_VERSION"

# Check Claude Code CLI
if ! command -v claude &> /dev/null; then
    echo ""
    echo "[2/7] Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
else
    echo ""
    echo "[2/7] Claude Code CLI already installed ✓"
fi

# Clone repo
echo ""
if [ -d "$INSTALL_DIR" ]; then
    echo "[3/7] Updating existing installation at $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "[3/7] Cloning work-agent to $INSTALL_DIR..."
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create virtual environment
echo ""
echo "[4/7] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "  ✓ Dependencies installed"

# Configure .env
echo ""
if [ ! -f ".env" ]; then
    echo "[5/7] Creating .env from template..."
    cp .env.example .env
    echo "  ✓ .env created — edit it with your credentials"
    echo ""
    echo "  Required credentials:"
    echo "    AGENT_SECRET     — any random string for API auth"
    echo "    SLACK_BOT_TOKEN  — from api.slack.com/apps (xoxb-... or xoxp-...)"
    echo "    SLACK_TEAM_ID    — from your Slack URL (T...)"
    echo "    SLACK_USER_ID    — from Slack profile → Copy member ID"
    echo ""
    echo "  Edit now:  nano $INSTALL_DIR/.env"
    NEEDS_CONFIG=1
else
    echo "[5/7] .env already exists ✓"
    NEEDS_CONFIG=0
fi

# Add to PATH
echo ""
echo "[6/7] Adding work-agent to PATH..."
if ! grep -q "work-agent/bin" "$SHELL_PROFILE" 2>/dev/null; then
    echo "" >> "$SHELL_PROFILE"
    echo "# work-agent CLI" >> "$SHELL_PROFILE"
    echo "export PATH=\"$INSTALL_DIR/bin:\$PATH\"" >> "$SHELL_PROFILE"
    echo "  ✓ Added to $SHELL_PROFILE"
else
    echo "  ✓ Already in PATH"
fi

# Run tests
echo ""
echo "[7/7] Running tests..."
if python -m pytest tests/ -q 2>&1 | tail -1 | grep -q "passed"; then
    echo "  ✓ All tests passed"
else
    echo "  ⚠ Some tests failed — check with: cd $INSTALL_DIR && python -m pytest tests/ -v"
fi

# Done
echo ""
echo "══════════════════════════════════════════"
echo "  ✓ work-agent installed successfully!"
echo "══════════════════════════════════════════"
echo ""
echo "  Location: $INSTALL_DIR"
echo ""

if [ "$NEEDS_CONFIG" -eq 1 ]; then
    echo "  Next steps:"
    echo "    1. Edit credentials:  nano $INSTALL_DIR/.env"
    echo "    2. Reload shell:      source $SHELL_PROFILE"
    echo "    3. Start the agent:   work-agent"
    echo ""
    echo "  See README for Slack app setup: https://github.com/predator-labs/work-agent#slack-app-setup"
else
    echo "  Reload your shell and run:"
    echo "    source $SHELL_PROFILE"
    echo "    work-agent              # start server"
    echo "    work-agent slack        # triage Slack"
    echo "    work-agent run-all      # full cycle"
fi
echo ""
