from pathlib import Path

# User skills directory alongside the config directory
USER_SKILLS_DIR = Path(__file__).parent.parent / "config" / "user_skills"


class SkillLoader:
    def __init__(self, skills_path: str | Path):
        self._path = Path(skills_path)
        self._user_path = USER_SKILLS_DIR

    def load(self, skill_name: str) -> str:
        # Check primary skills path first, then user skills
        for base in (self._path, self._user_path):
            skill_file = base / skill_name / "SKILL.md"
            if skill_file.exists():
                return skill_file.read_text()
        return ""

    def load_many(self, skill_names: list[str]) -> str:
        parts = []
        for name in skill_names:
            content = self.load(name)
            if content:
                parts.append(f"--- Skill: {name} ---\n{content}")
        return "\n\n".join(parts)

    def list_skills(self) -> list[str]:
        skills = set()
        for base in (self._path, self._user_path):
            if base.exists():
                for d in base.iterdir():
                    if d.is_dir() and (d / "SKILL.md").exists():
                        skills.add(d.name)
        return sorted(skills)
