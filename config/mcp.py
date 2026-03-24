from config.settings import Settings


def build_mcp_servers(settings: Settings) -> dict:
    """Build MCP server configuration dict for Claude Agent SDK."""
    servers = {}

    # Slack (stdio — official MCP server with bot token)
    if settings.slack_bot_token:
        servers["slack"] = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env": {
                "SLACK_BOT_TOKEN": settings.slack_bot_token,
                "SLACK_TEAM_ID": settings.slack_team_id,
            },
        }

    # Bitbucket
    if settings.bitbucket_username:
        servers["bitbucket"] = {
            "command": "npx",
            "args": ["-y", "bitbucket-mcp@latest"],
            "env": {
                "BITBUCKET_URL": settings.bitbucket_url,
                "BITBUCKET_WORKSPACE": settings.bitbucket_workspace,
                "BITBUCKET_USERNAME": settings.bitbucket_username,
                "BITBUCKET_PASSWORD": settings.bitbucket_password,
            },
        }

    # Atlassian (Jira + Confluence)
    if settings.jira_url:
        servers["atlassian"] = {
            "type": "sse",
            "url": "https://mcp.atlassian.com/v1/mcp",
        }

    # CircleCI
    if settings.circleci_token:
        servers["circleci"] = {
            "command": "npx",
            "args": ["-y", "@circleci/mcp-server-circleci@latest"],
            "env": {
                "CIRCLECI_TOKEN": settings.circleci_token,
                "CIRCLECI_BASE_URL": settings.circleci_base_url,
            },
        }

    # Codacy
    if settings.codacy_account_token:
        servers["codacy"] = {
            "command": "npx",
            "args": ["-y", "@codacy/codacy-mcp@latest"],
            "env": {
                "CODACY_ACCOUNT_TOKEN": settings.codacy_account_token,
            },
        }

    # Rollbar (docyt-server)
    if settings.rollbar_token_docyt_server:
        servers["rollbar-server"] = {
            "command": "npx",
            "args": ["-y", "@rollbar/mcp-server@latest"],
            "env": {
                "ROLLBAR_ACCESS_TOKEN": settings.rollbar_token_docyt_server,
            },
        }

    # Rollbar (docyt-mlai)
    if settings.rollbar_token_docyt_mlai:
        servers["rollbar-mlai"] = {
            "command": "npx",
            "args": ["-y", "@rollbar/mcp-server@latest"],
            "env": {
                "ROLLBAR_ACCESS_TOKEN": settings.rollbar_token_docyt_mlai,
            },
        }

    # DBHub
    servers["dbhub"] = {
        "command": "npx",
        "args": ["@bytebase/dbhub", "--transport", "stdio"],
    }

    # Deductive
    if settings.deductive_url:
        servers["deductive"] = {
            "type": "http",
            "url": settings.deductive_url,
        }

    # Figma
    servers["figma"] = {
        "type": "sse",
        "url": "https://mcp.figma.com/mcp",
    }

    return servers
