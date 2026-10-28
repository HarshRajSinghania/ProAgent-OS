from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str = "unknown"
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        raise NotImplementedError
