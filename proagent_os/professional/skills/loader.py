from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Skill:
    id: str
    name: str
    description: str
    body: str
    path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)
    runner: Optional[Callable[..., Any]] = None

    def prompt_snippet(self) -> str:
        return f"### Skill: {self.name} ({self.id})\n{self.description}\n\n{self.body[:2000]}"


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def _parse_skill_md(text: str) -> tuple[Dict[str, Any], str]:
    m = _FRONTMATTER.match(text)
    meta: Dict[str, Any] = {}
    body = text
    if m:
        fm, body = m.group(1), m.group(2)
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip("\"'")
    return meta, body.strip()


def _load_runner(skill_dir: Path) -> Optional[Callable[..., Any]]:
    run_py = skill_dir / "run.py"
    if not run_py.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"skill_{skill_dir.name}_run", run_py)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "run", None)


class SkillLoader:
    def __init__(self, directories: List[Path]) -> None:
        self.directories = directories
        self._skills: Dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        for root in self.directories:
            if not root.exists():
                continue
            for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                md = skill_dir / "SKILL.md"
                if not md.exists():
                    continue
                meta, body = _parse_skill_md(md.read_text(encoding="utf-8"))
                skill_id = meta.get("id") or skill_dir.name
                skill = Skill(
                    id=skill_id,
                    name=meta.get("name") or skill_dir.name.replace("_", " ").title(),
                    description=meta.get("description") or body.split("\n", 1)[0][:200],
                    body=body,
                    path=skill_dir,
                    metadata=meta,
                    runner=_load_runner(skill_dir),
                )
                self._skills[skill.id] = skill

    def list(self) -> List[Skill]:
        return list(self._skills.values())

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    async def invoke(self, skill_id: str, **kwargs: Any) -> Any:
        skill = self.get(skill_id)
        if not skill:
            raise KeyError(f"Unknown skill: {skill_id}")
        if not skill.runner:
            return {"skill_id": skill_id, "prompt": skill.prompt_snippet(), "note": "no run.py; returned prompt only"}
        result = skill.runner(**kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result
