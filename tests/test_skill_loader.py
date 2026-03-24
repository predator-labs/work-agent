import pytest
from shared.skill_loader import SkillLoader

@pytest.fixture
def skills_dir(tmp_path):
    skill = tmp_path / "sugam-code-review"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Sugam Code Review\nReview PRs for Docyt conventions.")
    skill2 = tmp_path / "running-unit-tests"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text("# Running Unit Tests\nUse dl-bexec for Docker tests.")
    return tmp_path

def test_load_skill(skills_dir):
    loader = SkillLoader(skills_dir)
    content = loader.load("sugam-code-review")
    assert "Sugam Code Review" in content
    assert "Review PRs" in content

def test_load_nonexistent_skill(skills_dir):
    loader = SkillLoader(skills_dir)
    content = loader.load("nonexistent-skill")
    assert content == ""

def test_load_multiple_skills(skills_dir):
    loader = SkillLoader(skills_dir)
    content = loader.load_many(["sugam-code-review", "running-unit-tests"])
    assert "Sugam Code Review" in content
    assert "Running Unit Tests" in content

def test_list_skills(skills_dir):
    loader = SkillLoader(skills_dir)
    skills = loader.list_skills()
    assert "sugam-code-review" in skills
    assert "running-unit-tests" in skills
