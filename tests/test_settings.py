import json
from config.settings import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_SECRET", "test-secret")
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setenv("SLACK_USER_ID", "U123")
    monkeypatch.setenv("JIRA_EMAIL", "test@docyt.com")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/tmp/vault")
    monkeypatch.setenv("REPOS_PATH", "/tmp/repos")
    monkeypatch.setenv("SKILLS_PATH", "/tmp/skills")

    settings = Settings()
    assert settings.anthropic_api_key == "test-key"
    assert settings.agent_secret == "test-secret"
    assert settings.ntfy_topic == "test-topic"
    assert settings.slack_user_id == "U123"


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_SECRET", "test-secret")
    settings = Settings()
    assert settings.ntfy_topic == "work-agent"
    assert settings.obsidian_vault_path == "/vault"
    assert settings.repos_path == "/repos"


def test_load_user_mcp_servers(tmp_path):
    import config.mcp as mcp_mod

    orig = mcp_mod.USER_MCP_CONFIG
    try:
        user_cfg = tmp_path / "user_mcp.json"
        user_cfg.write_text(json.dumps({
            "my-custom-server": {
                "command": "node",
                "args": ["my-server.js"],
            }
        }))
        mcp_mod.USER_MCP_CONFIG = user_cfg

        result = mcp_mod.load_user_mcp_servers()
        assert "my-custom-server" in result
        assert result["my-custom-server"]["command"] == "node"
    finally:
        mcp_mod.USER_MCP_CONFIG = orig


def test_load_user_mcp_servers_empty(tmp_path):
    import config.mcp as mcp_mod

    orig = mcp_mod.USER_MCP_CONFIG
    try:
        mcp_mod.USER_MCP_CONFIG = tmp_path / "nonexistent.json"
        result = mcp_mod.load_user_mcp_servers()
        assert result == {}
    finally:
        mcp_mod.USER_MCP_CONFIG = orig


def test_load_user_mcp_servers_invalid_json(tmp_path):
    import config.mcp as mcp_mod

    orig = mcp_mod.USER_MCP_CONFIG
    try:
        user_cfg = tmp_path / "bad.json"
        user_cfg.write_text("not valid json{{{")
        mcp_mod.USER_MCP_CONFIG = user_cfg

        result = mcp_mod.load_user_mcp_servers()
        assert result == {}
    finally:
        mcp_mod.USER_MCP_CONFIG = orig
