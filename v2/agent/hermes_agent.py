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
from agent.tools import TOOLS, dispatch_tool
from agent.llm_router import LLMRouter


# ---------------------------------------------------------------------------
# Hermes system prompt with XML tool schema
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """Build the Hermes-format system prompt with embedded tool definitions."""
    tools_xml = "\n".join(
        f"""    <tool>
      <name>{t['name']}</name>
      <description>{t['description']}</description>
      <parameters>{json.dumps(t['parameters'], indent=6)}</parameters>
    </tool>"""
        for t in TOOLS
    )

    return f"""You are LeadHunterOS, an autonomous B2B sales intelligence agent.
Your mission: identify high-quality leads that match the Ideal Customer Profile (ICP),
enrich them with verified contact data, score them, and produce actionable outreach.

You BEAT Gojiberry, Intently, and Unify GTM by:
- Running fully local on AMD hardware via Lemonade (zero cloud cost for inference)
- Using true agentic reasoning, not static enrichment pipelines
- Combining real-time signals (hiring, funding, technographics) with ICP scoring
- Producing personalized outreach, not generic templates

You operate in a strict Hermes ReAct loop:
  <thought>Reasoning about what to do next</thought>
  <tool_call>{{"name": "tool_name", "arguments": {{...}}}}</tool_call>
  [PAUSE - wait for tool_response]
  <tool_response>{{...}}</tool_response>
  ... repeat until done ...
  <final_answer>Complete structured result</final_answer>

RULES:
- NEVER call multiple tools simultaneously
- ALWAYS reason in <thought> before every action
- NEVER hallucinate contact data - only use verified tool results
- ONLY use US-based external APIs
- Local AMD inference via Lemonade is always preferred
- Escalate to cloud LLMs only for heavy reasoning tasks

Available tools:
<tools>
{tools_xml}
</tools>

Current date/time: {{datetime}}"""


# ---------------------------------------------------------------------------
# Core Hermes Agent
# ---------------------------------------------------------------------------

class HermesAgent:
    """True Hermes agent for B2B lead hunting.

    Uses Hermes XML tool-calling format with LLMRouter for
    Lemonade-first multi-backend inference.
    """

    MAX_STEPS = 15
    TOOL_CALL_RE = re.compile(
        r"<tool_call>\s*(.+?)\s*</tool_call>", re.DOTALL
    )
    FINAL_ANSWER_RE = re.compile(
        r"<final_answer>\s*(.+?)\s*</final_answer>", re.DOTALL
    )
    THOUGHT_RE = re.compile(
        r"<thought>\s*(.+?)\s*</thought>", re.DOTALL
    )

    def __init__(self) -> None:
        self.router = LLMRouter()
        self.session_id = str(uuid.uuid4())[:8]
        logger.info(f"HermesAgent initialized | session={self.session_id} | backends={self.router.available}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str, task_type: str = "normal") -> dict[str, Any]:
        """Run the agent on a task and return structured results."""
        logger.info(f"[{self.session_id}] Task: {task[:80]}...")

        system = build_system_prompt().replace(
            "{datetime}",
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

        steps = []
        final_answer = None

        for step in range(self.MAX_STEPS):
            logger.debug(f"[{self.session_id}] Step {step + 1}/{self.MAX_STEPS}")

            # Route to appropriate LLM
            response = self.router.route(messages, task_type=task_type)
            content = response.get("content", "")

            # Extract thought
            thought_match = self.THOUGHT_RE.search(content)
            thought = thought_match.group(1).strip() if thought_match else ""
            if thought:
                logger.info(f"[{self.session_id}] Thought: {thought[:100]}")

            # Check for final answer
            final_match = self.FINAL_ANSWER_RE.search(content)
            if final_match:
                final_answer = final_match.group(1).strip()
                logger.success(f"[{self.session_id}] Final answer reached at step {step + 1}")
                break

            # Check for tool call
            tool_match = self.TOOL_CALL_RE.search(content)
            if not tool_match:
                # No tool call and no final answer - ask model to continue
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Continue. Use a tool or provide <final_answer>."
                })
                continue

            # Parse and execute tool call
            try:
                call_data = json.loads(tool_match.group(1))
                tool_name = call_data["name"]
                tool_args = call_data.get("arguments", {})
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"[{self.session_id}] Bad tool call JSON: {e}")
                tool_response = {"error": f"Invalid tool call format: {e}"}
            else:
                logger.info(f"[{self.session_id}] Tool call: {tool_name}({list(tool_args.keys())})")
                tool_response = dispatch_tool(tool_name, tool_args)

            steps.append({
                "step": step + 1,
                "thought": thought,
                "tool": tool_name if tool_match else None,
                "args": tool_args if tool_match else {},
                "result": tool_response,
            })

            # Append assistant message + tool response in Hermes format
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": f"<tool_response>{json.dumps(tool_response)}</tool_response>"
            })

        else:
            logger.warning(f"[{self.session_id}] Max steps reached without final answer")
            final_answer = "Max reasoning steps reached. Partial results available in steps."

        return {
            "session_id": self.session_id,
            "task": task,
            "steps": steps,
            "final_answer": final_answer,
            "llm_backends_used": self.router.available,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def hunt_leads(
        self,
        company_domain: str | None = None,
        icp_description: str | None = None,
        enrichment_level: str = "full",
    ) -> dict[str, Any]:
        """High-level convenience method for lead hunting."""
        parts = ["Find, enrich, and score B2B leads."]
        if company_domain:
            parts.append(f"Target company domain: {company_domain}")
        if icp_description:
            parts.append(f"ICP: {icp_description}")
        parts.append(f"Enrichment level: {enrichment_level}")
        parts.append(
            "Return structured JSON with: leads list (name, title, company, email, "
            "linkedin_url, icp_score 0-100, signal, personalized_opener), "
            "total_found, avg_icp_score, recommended_sequence."
        )

        task = " ".join(parts)
        # Heavy enrichment uses cloud fallback if needed
        task_type = "heavy" if enrichment_level == "full" else "normal"
        return self.run(task, task_type=task_type)
