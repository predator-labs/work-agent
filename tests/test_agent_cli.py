# tests/test_agent_cli.py
from typer.testing import CliRunner
from unittest.mock import patch


runner = CliRunner()


def test_cli_help():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "AGENT_SECRET": "test"}):
        from agent import app
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run-all" in result.output or "Divyanshu" in result.output
