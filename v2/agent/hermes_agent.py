"""LeadHunterOS v2 - True Hermes Agent."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

import config
from agent.llm_router import LLMRouter
from agent.tools import TOOLS, dispatch_tool, get_tool_schema_xml


def _build_system_prompt() -> str:
    """Build the Hermes system prompt from the live tool registry."""
    return f"""You are LeadHunterOS.
Rules:
1) Use public signals first, then enrichment, then ranking/orchestration.
2) US scope only: {config.TARGET_COUNTRY}; exclude unclear/non-US leads.
3) Never invent data. No placeholders.
4) Save only leads meeting gates: icp_score >= {config.ICP_MIN_SCORE}.
5) Draft outreach only for verified, saved leads.
6) Max 3 tool calls per turn.

Tool call format:
<tool_call>{{"name":"tool_name","arguments":{{...}}}}</tool_call>

Finish with:
FINAL ANSWER: concise summary + top leads + actions + gaps

Tools:
{get_tool_schema_xml()}"""


MAX_ITERATIONS = config.AGENT_MAX_ITERATIONS
_VALID_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in TOOLS)
_MAX_TOOL_CALLS_PER_TURN = 3


class HermesAgent:
    """True Hermes agent with XML tool-calling and ReAct loop."""

    def __init__(self, preferred_backend: str | None = None) -> None:
        self.router = LLMRouter(preferred_backend=preferred_backend)
        self.session_id = str(uuid.uuid4())[:8]
        self.system_prompt = _build_system_prompt()
        logger.info(
            f"HermesAgent initialized | session={self.session_id} "
            f"| backends={self.router.available_backends} | tools={len(TOOLS)}"
        )

    def run(self, objective: str) -> dict[str, Any]:
        """Run the full Hermes ReAct loop for the given objective."""
        logger.info(f"[{self.session_id}] Starting agent run")
        logger.info(f"[{self.session_id}] Objective: {objective[:120]}")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": objective},
        ]

        leads_saved: list[dict[str, Any]] = []
        iterations = 0
        last_response: dict[str, Any] = {}
        no_progress_turns = 0

        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"[{self.session_id}] Iteration {iterations}/{MAX_ITERATIONS}")

            try:
                response = self.router.route(messages)
            except RuntimeError as exc:
                logger.error(f"[{self.session_id}] All backends failed: {exc}")
                break

            last_response = response
            content = response["content"]
            logger.info(
                f"[{self.session_id}] Response from "
                f"{response['backend']}/{response['model']} ({len(content)} chars)"
            )

            if "FINAL ANSWER:" in content:
                messages.append({"role": "assistant", "content": content})
                logger.success(f"[{self.session_id}] Agent reached final answer")
                break

            tool_calls, parse_errors = self._parse_tool_calls(content)
            messages.append({"role": "assistant", "content": self._assistant_history_entry(content, tool_calls)})
            if not tool_calls and not parse_errors:
                no_progress_turns += 1
                logger.warning(f"[{self.session_id}] No tool call or final answer. Nudging.")
                if no_progress_turns >= 2:
                    messages.append({
                        "role": "user",
                        "content": (
                            "No valid tool calls detected twice in a row. "
                            "Return FINAL ANSWER now with best verified findings and explicit gaps."
                        ),
                    })
                    continue
                messages.append({
                    "role": "user",
                    "content": (
                        "Please use a tool or write FINAL ANSWER: with your results. "
                        'Tool call format: <tool_call>{"name": "...", "arguments": {...}}</tool_call>.'
                    ),
                })
                continue

            no_progress_turns = 0
            tool_responses: list[str] = []
            for err in parse_errors:
                tool_responses.append(
                    f"<tool_response>\n"
                    f"Parse error: {err}\n"
                    f"Re-emit the tool_call with valid JSON.\n"
                    f"</tool_response>"
                )

            for call in tool_calls[:_MAX_TOOL_CALLS_PER_TURN]:
                tool_name = call.get("name", "")
                tool_args = call.get("arguments", {}) or {}
                args_preview = str(tool_args)[:200]
                logger.info(f"[{self.session_id}] Calling tool: {tool_name}({args_preview})")

                if tool_name not in _VALID_TOOL_NAMES:
                    result: dict[str, Any] = {
                        "ok": False,
                        "error": f"Unknown tool: {tool_name}",
                        "available_tools": sorted(_VALID_TOOL_NAMES),
                    }
                else:
                    try:
                        result = dispatch_tool(tool_name, tool_args)
                        if tool_name == "save_lead" and result.get("saved"):
                            leads_saved.append(result.get("lead", result))
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc), "tool": tool_name}
                        logger.warning(f"[{self.session_id}] Tool {tool_name} error: {exc}")

                compact_result = self._compact_tool_result(result)
                tool_responses.append(
                    f"<tool_response>\n"
                    f"Tool: {tool_name}\n"
                    f"Result: {json.dumps(compact_result, separators=(',', ':'), default=str)}\n"
                    f"</tool_response>"
                )
            if len(tool_calls) > _MAX_TOOL_CALLS_PER_TURN:
                tool_responses.append(
                    "<tool_response>\n"
                    "Tool: scheduler\n"
                    f"Result: skipped {len(tool_calls) - _MAX_TOOL_CALLS_PER_TURN} extra tool calls this turn to preserve local context.\n"
                    "</tool_response>"
                )

            messages.append({"role": "user", "content": self._fit_tool_responses(tool_responses)})

        if iterations >= MAX_ITERATIONS:
            logger.warning(f"[{self.session_id}] Hit max iterations ({MAX_ITERATIONS})")

        return {
            "session_id": self.session_id,
            "objective": objective,
            "iterations": iterations,
            "leads_saved": len(leads_saved),
            "leads": leads_saved,
            "backend_used": last_response.get("backend", "none"),
            "model_used": last_response.get("model", "none"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_tool_calls(self, content: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Extract tool calls and return malformed call errors separately."""
        pattern = r"<tool_call>\s*(.+?)\s*</tool_call>"
        matches = re.findall(pattern, content, re.DOTALL)
        calls: list[dict[str, Any]] = []
        errors: list[str] = []

        for raw in matches:
            try:
                call = json.loads(raw)
                if isinstance(call, dict) and "name" in call:
                    calls.append(call)
                else:
                    errors.append(f"missing 'name' key: {raw[:100]}")
            except json.JSONDecodeError as exc:
                errors.append(f"JSON error ({exc}): {raw[:100]}")
                logger.warning(f"Failed to parse tool_call JSON: {exc} | raw: {raw[:100]}")

        return calls, errors

    def _assistant_history_entry(self, content: str, tool_calls: list[dict[str, Any]]) -> str:
        """Keep only the tool-call portion of assistant turns to preserve local context."""
        if not tool_calls:
            return content[:240] + ("...[truncated]" if len(content) > 240 else "")

        tool_blocks: list[str] = []
        for call in tool_calls[:3]:
            tool_blocks.append(
                "<tool_call>"
                + json.dumps(call, separators=(",", ":"), default=str)
                + "</tool_call>"
            )
        if len(tool_calls) > 3:
            tool_blocks.append("<tool_call>{\"note\":\"additional tool calls truncated\"}</tool_call>")
        return "\n".join(tool_blocks)

    def _compact_tool_result(self, value: Any, depth: int = 0) -> Any:
        """Keep tool observations useful but small enough for local 4096-token models."""
        if depth > 4:
            return str(value)[:180]
        if isinstance(value, str):
            return value if len(value) <= 280 else value[:280] + "...[truncated]"
        if isinstance(value, list):
            compact = [self._compact_tool_result(item, depth + 1) for item in value[:2]]
            if len(value) > 2:
                compact.append({"truncated_count": len(value) - 2})
            return compact
        if isinstance(value, dict):
            compact_dict: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"raw_signal_data", "description", "html", "content"}:
                    compact_dict[key] = str(item)[:180] + ("...[truncated]" if len(str(item)) > 180 else "")
                else:
                    compact_dict[key] = self._compact_tool_result(item, depth + 1)
            return compact_dict
        return value

    def _fit_tool_responses(self, responses: list[str], max_chars: int = 3200) -> str:
        combined = "\n".join(responses)
        if len(combined) <= max_chars:
            return combined
        kept: list[str] = []
        used = 0
        for response in responses:
            if used + len(response) > max_chars:
                break
            kept.append(response)
            used += len(response)
        kept.append("<tool_response>Result: observation batch truncated to fit local context.</tool_response>")
        return "\n".join(kept)
