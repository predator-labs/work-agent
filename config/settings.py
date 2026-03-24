from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core
    anthropic_api_key: str
    agent_secret: str

    # Notifications
    ntfy_topic: str = "divyanshu-agent"

    # Identity
    slack_user_id: str = ""
    jira_email: str = "divyanshu.sharma@docyt.com"
    git_author_name: str = "Divyanshu Sharma"
    git_author_email: str = "divyanshu.sharma@docyt.com"
    git_committer_name: str = "Divyanshu Sharma"
    git_committer_email: str = "divyanshu.sharma@docyt.com"

    # Paths
    obsidian_vault_path: str = "/vault"
    repos_path: str = "/repos"
    skills_path: str = "/repos/docyt_ops/ai/skills"
    memory_path: str = "/repos/.claude/projects/-Users-divyanshusharma-docyt/memory"

    # MCP: Bitbucket
    bitbucket_url: str = "https://api.bitbucket.org/2.0"
    bitbucket_workspace: str = "kmnss"
    bitbucket_username: str = ""
    bitbucket_password: str = ""

    # MCP: Atlassian
    confluence_url: str = ""
    confluence_username: str = ""
    confluence_api_token: str = ""
    jira_url: str = ""
    jira_username: str = ""
    jira_api_token: str = ""

    # MCP: CircleCI
    circleci_token: str = ""
    circleci_base_url: str = "https://app.circleci.com"

    # MCP: Codacy
    codacy_account_token: str = ""

    # MCP: Rollbar
    rollbar_token_docyt_server: str = ""
    rollbar_token_docyt_mlai: str = ""

    # MCP: Slack
    slack_bot_token: str = ""
    slack_team_id: str = ""

    # MCP: Todoist
    todoist_api_key: str = ""

    # MCP: Deductive
    deductive_url: str = "https://docyt.deductive.ai/api/mcp"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
