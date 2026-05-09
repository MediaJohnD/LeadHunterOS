"""LeadHunterOS v2 - True Hermes Agent

Implements a true Hermes agent with:
  - Hermes XML tool-calling format (<tools>, <tool_call>, <tool_response>)
  - Thought -> Action -> Observation ReAct loop
  - LLMRouter for multi-backend support

LLM priority (via LLMRouter):
  1. Lemonade local AMD (primary - always tried first)
  2. Claude Opus via Anthropic API (heavy tasks)
  3. OpenAI GPT-4o via API (fallback)
  4. Perplexity via API (research/search tasks)

All external tool calls use US-based APIs only.
Local models from any origin are acceptable.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

import config
from agent.tools import dispatch_tool, get_tool_schema_xml
from agent.llm_router import LLMRouter


# ---------------------------------------------------------------------------
# Hermes system prompt - defines the agent's tool-calling contract
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = """You are LeadHunterOS, a B2B lead-hunting Hermes agent.
You beat Gojiberry, Intently, and Unify GTM by combining local AMD inference
with real-time web research, ICP scoring, and personalized outreach.

You have access to tools. Use them by emitting XML in this exact format:

<tool_call>
{"name": "tool_name", "arguments": {"param": "value"}}
</tool_call>

After a tool is called you will receive a <tool_response> with the result.
Think step by step. When you have enough information to complete the objective,
write your final answer starting with FINAL ANSWER:

Use public-signal tools first, then enrich, score, save qualified leads, and
draft outreach. Never invent tool names or parameters; use only this schema:

{tool_schema}
"""

# Max tool-call iterations before giving up
MAX_ITERATIONS = 15


class HermesAgent:
    """True Hermes agent with XML tool-calling and ReAct loop."""

    def __init__(self, preferred_backend: str | None = None) -> None:
        self.router = LLMRouter(preferred_backend=preferred_backend)
        self.session_id = str(uuid.uuid4())[:8]
        # Use available_backends (correct attribute name from LLMRouter)
        logger.info(
            f"HermesAgent initialized | session={self.session_id} "
            f"| backends={self.router.available_backends}"
        )

    def run(self, objective: str) -> dict[str, Any]:
        """Run the full Hermes ReAct loop for the given objective."""
        logger.info(f"[{self.session_id}] Starting agent run")
        logger.info(f"[{self.session_id}] Objective: {objective[:120]}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(tool_schema=get_tool_schema_xml())},
            {"role": "user", "content": objective},
        ]

        leads_saved: list[dict] = []
        iterations = 0

        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"[{self.session_id}] Iteration {iterations}/{MAX_ITERATIONS}")

            # Call LLM (local Lemonade first, then cloud fallbacks)
            try:
                response = self.router.route(messages)
            except RuntimeError as e:
                logger.error(f"[{self.session_id}] All backends failed: {e}")
                break

            content = response["content"]
            backend = response["backend"]
            model = response["model"]
            logger.info(f"[{self.session_id}] Response from {backend}/{model} ({len(content)} chars)")

            # Add assistant message to history
            messages.append({"role": "assistant", "content": content})

            # Check for final answer
            if "FINAL ANSWER:" in content:
                logger.success(f"[{self.session_id}] Agent reached final answer")
                break

            # Parse and execute tool calls
            tool_calls = self._parse_tool_calls(content)
            if not tool_calls:
                # No tool calls and no final answer - nudge the agent
                logger.warning(f"[{self.session_id}] No tool call or final answer. Nudging.")
                messages.append({
                    "role": "user",
                    "content": (
                        "Please use a tool or write FINAL ANSWER: with your results. "
                        "Remember to format tool calls as <tool_call>{...}</tool_call>."
                    ),
                })
                continue

            # Execute each tool call and add responses
            tool_responses = []
            for call in tool_calls:
                tool_name = call.get("name", "")
                tool_args = call.get("arguments", {})
                logger.info(f"[{self.session_id}] Calling tool: {tool_name}({tool_args})")

                try:
                    result = dispatch_tool(tool_name, tool_args)
                    # Track saved leads for summary
                    if tool_name == "save_lead" and result.get("saved"):
                        leads_saved.append(result)
                except Exception as e:
                    result = {"error": str(e), "tool": tool_name}
                    logger.warning(f"[{self.session_id}] Tool {tool_name} error: {e}")

                tool_responses.append(
                    f"<tool_response>\n"
                    f"Tool: {tool_name}\n"
                    f"Result: {json.dumps(result, indent=2)}\n"
                    f"</tool_response>"
                )

            # Feed all tool responses back to the agent
            combined = "\n".join(tool_responses)
            messages.append({"role": "user", "content": combined})

        if iterations >= MAX_ITERATIONS:
            logger.warning(f"[{self.session_id}] Hit max iterations ({MAX_ITERATIONS})")

        return {
            "session_id": self.session_id,
            "objective": objective,
            "iterations": iterations,
            "leads_saved": len(leads_saved),
            "leads": leads_saved,
            "backend_used": response.get("backend", "unknown") if iterations > 0 else "none",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_tool_calls(self, content: str) -> list[dict]:
        """Extract all <tool_call>...</tool_call> blocks from LLM output."""
        pattern = r"<tool_call>\s*(.+?)\s*</tool_call>"
        matches = re.findall(pattern, content, re.DOTALL)
        calls = []
        for raw in matches:
            try:
                call = json.loads(raw)
                calls.append(call)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool_call JSON: {e} | raw: {raw[:100]}")
        return calls
