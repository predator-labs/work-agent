from pathlib import Path

# User rules file alongside the config directory
USER_RULES_FILE = Path(__file__).parent.parent / "config" / "user_rules.md"


class ContextLoader:
    def __init__(self, repos_path: str | Path):
        self._repos = Path(repos_path)

    def load_root(self) -> str:
        claude_md = self._repos / "CLAUDE.md"
        if claude_md.exists():
            return claude_md.read_text()
        return ""

    def load_service(self, service_name: str) -> str:
        service_dir = self._repos / service_name
        if not service_dir.exists():
            return ""
        parts = []
        for filename in ["CLAUDE.md", "AGENTS.md"]:
            f = service_dir / filename
            if f.exists():
                parts.append(f.read_text())
        rules_dir = service_dir / ".claude" / "rules"
        if rules_dir.exists():
            for rule_file in sorted(rules_dir.glob("*.md")) + sorted(rules_dir.glob("*.mdc")):
                parts.append(f"--- Rule: {rule_file.name} ---\n{rule_file.read_text()}")
        return "\n\n".join(parts)

    def load_memory(self, memory_path: str | Path) -> str:
        memory_dir = Path(memory_path)
        if not memory_dir.exists():
            return ""
        parts = []
        for f in sorted(memory_dir.glob("*.md")):
            parts.append(f"--- Memory: {f.stem} ---\n{f.read_text()}")
        return "\n\n".join(parts)

    def build_context(self, service: str = "", memory_path: str | Path = "") -> str:
        parts = [self.load_root()]
        if service:
            service_context = self.load_service(service)
            if service_context:
                parts.append(service_context)
        if memory_path:
            memory_context = self.load_memory(memory_path)
            if memory_context:
                parts.append(memory_context)
        # Append user-defined rules
        user_rules = load_user_rules()
        if user_rules:
            parts.append(user_rules)
        return "\n\n".join(p for p in parts if p)


def load_user_rules() -> str:
    """Load user-defined rules from config/user_rules.md."""
    if not USER_RULES_FILE.exists():
        return ""
    content = USER_RULES_FILE.read_text().strip()
    if content:
        return f"## User Rules\n{content}"
    return ""
