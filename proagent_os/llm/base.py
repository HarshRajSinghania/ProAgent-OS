from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class ToolCall:
    """OpenAI-style tool call (function)."""

    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_openai(self) -> Dict[str, Any]:
        args = self.raw_arguments or json.dumps(self.arguments, ensure_ascii=False)
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": args},
        }


@dataclass
class LLMMessage:
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # tool role name (optional)

    def to_openai(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": self.role}
        if self.role == "assistant" and self.tool_calls:
            msg["content"] = self.content  # may be None
            msg["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        elif self.role == "tool":
            msg["content"] = self.content if self.content is not None else ""
            if self.tool_call_id:
                msg["tool_call_id"] = self.tool_call_id
            if self.name:
                msg["name"] = self.name
        else:
            msg["content"] = self.content if self.content is not None else ""
        return msg


@dataclass
class LLMResponse:
    content: Optional[str] = None
    model: str = "unknown"
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[Dict[str, Any]] = None
    tool_calls: List[ToolCall] = field(default_factory=list)


ToolChoice = Union[str, Dict[str, Any], None]


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: ToolChoice = None,
    ) -> LLMResponse:
        raise NotImplementedError


def parse_tool_arguments(raw: Any) -> tuple[Dict[str, Any], str]:
    """Return (parsed_dict, raw_json_string)."""
    if raw is None:
        return {}, "{}"
    if isinstance(raw, dict):
        return raw, json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, str):
        s = raw.strip() or "{}"
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed, s
            return {"value": parsed}, s
        except json.JSONDecodeError:
            return {"_raw": s}, s
    return {"value": raw}, json.dumps(raw, default=str)
