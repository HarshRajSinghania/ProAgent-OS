from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class AgentSpec:
    id: str
    role: str
    tools: List[str] = field(default_factory=list)
    system_prompt: str = ""
    description: str = ""


class AgentRegistry:
    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path
        self._agents: Dict[str, AgentSpec] = {}
        if config_path:
            self.load(config_path)

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in data.get("agents", []):
            spec = AgentSpec(
                id=item["id"],
                role=item.get("role", item["id"]),
                tools=list(item.get("tools") or []),
                system_prompt=item.get("system_prompt") or item.get("system_prompt_template") or "",
                description=item.get("description") or "",
            )
            self._agents[spec.id] = spec

    def merge_file(self, path: Path) -> None:
        self.load(path)

    def register(self, spec: AgentSpec) -> None:
        self._agents[spec.id] = spec

    def get(self, agent_id: str) -> Optional[AgentSpec]:
        return self._agents.get(agent_id)

    def list(self) -> List[AgentSpec]:
        return list(self._agents.values())
