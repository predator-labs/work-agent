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


def test_user_skills_loaded(tmp_path):
    import shared.skill_loader as sl_mod

    orig = sl_mod.USER_SKILLS_DIR
    try:
        user_dir = tmp_path / "user_skills"
        user_skill = user_dir / "my-custom-skill"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text("# My Custom Skill\nDo custom things.")
        sl_mod.USER_SKILLS_DIR = user_dir

        loader = SkillLoader(tmp_path / "nonexistent")
        content = loader.load("my-custom-skill")
        assert "My Custom Skill" in content

        skills = loader.list_skills()
        assert "my-custom-skill" in skills
    finally:
        sl_mod.USER_SKILLS_DIR = orig


def test_primary_skills_override_user(tmp_path):
    import shared.skill_loader as sl_mod

    orig = sl_mod.USER_SKILLS_DIR
    try:
        # Create same skill name in both paths
        primary = tmp_path / "primary"
        primary_skill = primary / "shared-skill"
        primary_skill.mkdir(parents=True)
        (primary_skill / "SKILL.md").write_text("PRIMARY version")

        user_dir = tmp_path / "user"
        user_skill = user_dir / "shared-skill"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text("USER version")

        sl_mod.USER_SKILLS_DIR = user_dir

        loader = SkillLoader(primary)
        content = loader.load("shared-skill")
        # Primary should win
        assert "PRIMARY version" in content
    finally:
        sl_mod.USER_SKILLS_DIR = orig
