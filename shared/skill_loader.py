from pathlib import Path


class SkillLoader:
    def __init__(self, skills_path: str | Path):
        self._path = Path(skills_path)

    def load(self, skill_name: str) -> str:
        skill_file = self._path / skill_name / "SKILL.md"
        if not skill_file.exists():
            return ""
        return skill_file.read_text()

    def load_many(self, skill_names: list[str]) -> str:
        parts = []
        for name in skill_names:
            content = self.load(name)
            if content:
                parts.append(f"--- Skill: {name} ---\n{content}")
        return "\n\n".join(parts)

    def list_skills(self) -> list[str]:
        if not self._path.exists():
            return []
        return [d.name for d in sorted(self._path.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()]
