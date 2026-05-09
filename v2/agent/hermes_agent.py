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
    return f"""You are LeadHunterOS, a B2B lead-hunting Hermes agent.
Your goal: discover, score, and prepare warm outreach for high-fit B2B leads
using public signals. No cold lists, no guessing.

Signal strategy:
  1. Public signals first: jobs, funding, news, Reddit, HN, GitHub, Product Hunt, public profiles.
  2. Public enrichment second: company websites, team pages, email candidates, MX checks.
  3. Paid fallbacks only when public data is insufficient: Apollo, Hunter.
  4. Score every candidate with score_lead.
  5. Save only qualified leads with icp_score >= {config.ICP_MIN_SCORE}.
  6. Draft outreach after scoring and saving.

Use tools by emitting XML in this exact Hermes format:

<tool_call>
{{"name": "tool_name", "arguments": {{"param": "value"}}}}
</tool_call>

After a tool is called you will receive a <tool_response> with the result.
Multiple tool calls may be emitted per turn; each gets its own response.
If a tool_call has malformed JSON, you will receive a parse error. Fix and re-emit it.

Think step by step. When the objective is complete, write:
FINAL ANSWER: <summary of leads found, scored, saved, and outreach drafted>

Never invent tool names or parameters. Use only this schema:

{get_tool_schema_xml()}
"""


MAX_ITERATIONS = config.AGENT_MAX_ITERATIONS
_VALID_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in TOOLS)


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

            messages.append({"role": "assistant", "content": content})

            if "FINAL ANSWER:" in content:
                logger.success(f"[{self.session_id}] Agent reached final answer")
                break

            tool_calls, parse_errors = self._parse_tool_calls(content)
            if not tool_calls and not parse_errors:
                logger.warning(f"[{self.session_id}] No tool call or final answer. Nudging.")
                messages.append({
                    "role": "user",
                    "content": (
                        "Please use a tool or write FINAL ANSWER: with your results. "
                        'Tool call format: <tool_call>{"name": "...", "arguments": {...}}</tool_call>.'
                    ),
                })
                continue

            tool_responses: list[str] = []
            for err in parse_errors:
                tool_responses.append(
                    f"<tool_response>\n"
                    f"Parse error: {err}\n"
                    f"Re-emit the tool_call with valid JSON.\n"
                    f"</tool_response>"
                )

            for call in tool_calls:
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

                tool_responses.append(
                    f"<tool_response>\n"
                    f"Tool: {tool_name}\n"
                    f"Result: {json.dumps(result, indent=2, default=str)}\n"
                    f"</tool_response>"
                )

            messages.append({"role": "user", "content": "\n".join(tool_responses)})

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
