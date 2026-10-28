from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from proagent_os.db import dumps, get_db, loads, new_id, utcnow
from proagent_os.harness.memory import ConversationMemory
from proagent_os.harness.registry import AgentRegistry
from proagent_os.llm.base import LLMMessage, LLMProvider
from proagent_os.professional.brand.store import BrandStore
from proagent_os.professional.skills.loader import SkillLoader
from proagent_os.professional.tools.base import ToolContext, ToolRegistry


def _extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


class Orchestrator:
    """Planner → Specialist agents → Aggregator run loop."""

    def __init__(
        self,
        llm: LLMProvider,
        agents: AgentRegistry,
        tools: ToolRegistry,
        skills: SkillLoader,
    ) -> None:
        self.llm = llm
        self.agents = agents
        self.tools = tools
        self.skills = skills
        self.memory = ConversationMemory()
        self.brand = BrandStore()
        self.db = get_db()

    async def run_task(
        self,
        tenant_id: str,
        input_text: str,
        *,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not conversation_id:
            conversation_id = self.memory.create_conversation(tenant_id, title=input_text[:80])
        self.memory.add_message(conversation_id, "user", input_text)

        task_id = new_id("task")
        now = utcnow()
        self.db.insert(
            "tasks",
            {
                "id": task_id,
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "status": "running",
                "input": input_text,
                "plan_json": "[]",
                "result": "",
                "trace_json": "[]",
                "created_at": now,
                "updated_at": now,
            },
        )

        trace: List[Dict[str, Any]] = []
        brand = self.brand.get(tenant_id)
        brand_block = brand.prompt_block() if brand else f"Tenant: {tenant_id}"

        # 1) Plan
        plan = await self._plan(input_text, brand_block, trace)
        self.db.update(
            "tasks",
            {"plan_json": dumps(plan), "updated_at": utcnow()},
            "id=?",
            (task_id,),
        )

        # 2) Execute specialist steps
        step_results: List[Dict[str, Any]] = []
        ctx = ToolContext(tenant_id=tenant_id, task_id=task_id)
        for step in plan.get("steps", []):
            agent_id = step.get("agent", "researcher")
            goal = step.get("goal", input_text)
            result = await self._run_specialist(agent_id, goal, input_text, brand_block, ctx, trace)
            step_results.append({"agent": agent_id, "goal": goal, "result": result})

        # 3) Aggregate
        final = await self._aggregate(input_text, step_results, brand_block, trace)

        self.db.update(
            "tasks",
            {
                "status": "completed",
                "result": final,
                "trace_json": dumps(trace),
                "updated_at": utcnow(),
            },
            "id=?",
            (task_id,),
        )
        self.memory.add_message(conversation_id, "assistant", final, meta={"task_id": task_id})

        return {
            "task_id": task_id,
            "conversation_id": conversation_id,
            "status": "completed",
            "plan": plan,
            "result": final,
            "trace": trace,
        }

    async def _plan(self, task: str, brand_block: str, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        planner = self.agents.get("planner")
        system = (planner.system_prompt if planner else "") or (
            "You are the Planner agent. Create a short plan as JSON with keys "
            "`steps` (list of {agent, goal, tools}) and `summary`."
        )
        messages = [
            LLMMessage(role="system", content=f"{system}\n\n{brand_block}"),
            LLMMessage(role="user", content=f"Task: {task}\n\nAvailable agents: {[a.id for a in self.agents.list()]}"),
        ]
        resp = await self.llm.chat(messages)
        parsed = _extract_json(resp.content) or {
            "steps": [
                {"agent": "researcher", "goal": task, "tools": ["kb_search"]},
                {"agent": "analyst", "goal": "Analyze and recommend", "tools": ["emit_recommendation"]},
            ],
            "summary": "Default two-step plan",
        }
        trace.append({"phase": "plan", "model": resp.model, "raw": resp.content, "parsed": parsed})
        return parsed

    async def _run_specialist(
        self,
        agent_id: str,
        goal: str,
        task: str,
        brand_block: str,
        ctx: ToolContext,
        trace: List[Dict[str, Any]],
    ) -> str:
        spec = self.agents.get(agent_id)
        tools_allowed = (spec.tools if spec else []) or ["kb_search", "clock"]
        skill_bits = "\n\n".join(s.prompt_snippet() for s in self.skills.list()[:5])
        system = (spec.system_prompt if spec else "") or f"You are the {agent_id} specialist."
        system += (
            "\nYou may use tools. When you need a tool, reply with JSON: "
            '{"thought":"...","tool_calls":[{"name":"...","arguments":{...}}],"answer":""}. '
            "When done, put the final answer in `answer` and leave tool_calls empty."
            f"\nAllowed tools: {tools_allowed}\n\n{brand_block}\n\nSkills:\n{skill_bits}"
        )
        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=f"Overall task: {task}\nYour goal: {goal}"),
        ]

        tool_outputs: List[Dict[str, Any]] = []
        answer = ""
        for round_i in range(3):
            resp = await self.llm.chat(messages)
            parsed = _extract_json(resp.content)
            trace.append(
                {
                    "phase": "specialist",
                    "agent": agent_id,
                    "round": round_i,
                    "model": resp.model,
                    "raw": resp.content[:2000],
                }
            )
            if not isinstance(parsed, dict):
                answer = resp.content
                break
            calls = parsed.get("tool_calls") or []
            if parsed.get("answer") and not calls:
                answer = parsed["answer"]
                break
            if not calls:
                answer = parsed.get("answer") or resp.content
                break
            for call in calls:
                name = call.get("name")
                if name not in tools_allowed and tools_allowed:
                    # still allow emit_recommendation / kb_search commonly
                    if name not in {"kb_search", "emit_recommendation", "clock"}:
                        tool_outputs.append({"name": name, "error": "tool not allowed"})
                        continue
                result = await self.tools.invoke(name, call.get("arguments") or {}, ctx)
                tool_outputs.append({"name": name, "ok": result.ok, "output": result.output, "error": result.error})
                trace.append({"phase": "tool", "agent": agent_id, "tool": name, "result": result.output, "error": result.error})
            messages.append(LLMMessage(role="assistant", content=resp.content))
            messages.append(
                LLMMessage(
                    role="user",
                    content="Tool results:\n" + json.dumps(tool_outputs[-len(calls):], ensure_ascii=False) + "\nContinue; finish with answer JSON if done.",
                )
            )
            # After tools, ask once more for final answer without forcing more tools
            if round_i == 1:
                # nudge default mock path
                pass

        if not answer:
            answer = json.dumps({"goal": goal, "tool_outputs": tool_outputs}, ensure_ascii=False)
        return answer

    async def _aggregate(
        self,
        task: str,
        step_results: List[Dict[str, Any]],
        brand_block: str,
        trace: List[Dict[str, Any]],
    ) -> str:
        agg = self.agents.get("aggregator")
        system = (agg.system_prompt if agg else "") or (
            "You are the Aggregator. Synthesize specialist results into a clear final answer."
        )
        messages = [
            LLMMessage(role="system", content=f"{system}\n\n{brand_block}"),
            LLMMessage(
                role="user",
                content=f"Task: {task}\n\nSpecialist results:\n{json.dumps(step_results, ensure_ascii=False)[:6000]}",
            ),
        ]
        resp = await self.llm.chat(messages)
        trace.append({"phase": "aggregate", "model": resp.model, "raw": resp.content[:2000]})
        return resp.content
