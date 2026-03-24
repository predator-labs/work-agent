import os
import pytest
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
    assert settings.ntfy_topic == "divyanshu-agent"
    assert settings.obsidian_vault_path == "/vault"
    assert settings.repos_path == "/repos"
