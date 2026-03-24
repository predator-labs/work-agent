import pytest
from pathlib import Path
from shared.context_loader import ContextLoader

@pytest.fixture
def repos_dir(tmp_path):
    root_claude = tmp_path / "CLAUDE.md"
    root_claude.write_text("# Root CLAUDE.md\nDocyt monorepo conventions.")
    server = tmp_path / "docyt_server"
    server.mkdir()
    (server / "CLAUDE.md").write_text("# docyt_server\nRuby 2.7.5, Rails 4.2.8.")
    mlai = tmp_path / "docyt-mlai"
    mlai.mkdir()
    (mlai / "CLAUDE.md").write_text("# docyt-mlai\nPython 3.12, Flask.")
    dashboards = tmp_path / "dashboards-service"
    dashboards.mkdir()
    (dashboards / "AGENTS.md").write_text("# Dashboards\nWidget patterns.")
    memory_dir = tmp_path / ".claude" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "feedback_pr_review.md").write_text("Fix issues in code, don't post comments.")
    (memory_dir / "feedback_no_rubocop_disable.md").write_text("No rubocop:disable.")
    return tmp_path

def test_load_root_context(repos_dir):
    loader = ContextLoader(repos_dir)
    content = loader.load_root()
    assert "Root CLAUDE.md" in content

def test_load_service_context(repos_dir):
    loader = ContextLoader(repos_dir)
    content = loader.load_service("docyt_server")
    assert "Ruby 2.7.5" in content

def test_load_service_agents_md(repos_dir):
    loader = ContextLoader(repos_dir)
    content = loader.load_service("dashboards-service")
    assert "Widget patterns" in content

def test_load_service_nonexistent(repos_dir):
    loader = ContextLoader(repos_dir)
    content = loader.load_service("nonexistent-service")
    assert content == ""

def test_load_memory_files(repos_dir):
    loader = ContextLoader(repos_dir)
    content = loader.load_memory(repos_dir / ".claude" / "memory")
    assert "Fix issues in code" in content
    assert "No rubocop:disable" in content

def test_build_context_for_service(repos_dir):
    loader = ContextLoader(repos_dir)
    context = loader.build_context(service="docyt_server", memory_path=repos_dir / ".claude" / "memory")
    assert "Root CLAUDE.md" in context
    assert "Ruby 2.7.5" in context
    assert "Fix issues in code" in context
