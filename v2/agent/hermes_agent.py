"""LeadHunterOS v2 - Hermes ReAct Agent

Implements a Thought -> Action -> Observation loop (ReAct pattern)
compatible with Hermes 3 / nous-hermes2 prompt format.

LLM priority:
  1. Local Ollama (primary - always tried first)
  2. Claude via Anthropic API (fallback only)

All tool calls are US-based APIs only.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

import config
from agent.tools import TOOLS, dispatch_tool


# ── Hermes 3 system prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are LeadHunterOS, an autonomous B2B sales intelligence agent.
Your job: identify high-quality leads that match the ICP, enrich them,
score them, and prepare personalized outreach.

You operate in a ReAct loop:
  <thought>Your reasoning about what to do next</thought>
  <tool_call>{"name": "tool_name", "arguments": {"arg": "value"}}</tool_call>

After each tool call you will receive:
  <observation>result of the tool call</observation>

When you have completed the task, respond with:
  <thought>I have completed the lead hunting cycle.</thought>
  <final_answer>Summary of leads found and actions taken.</final_answer>

Available tools:
{tool_descriptions}

Rules:
- Only use US-based data sources
- Never make up company or contact data
- Always enrich before scoring
- Score leads 0-100; only qualify leads scoring >= {icp_threshold}
- Be concise in thoughts; be precise in tool calls
"""


class HermesAgent:
    """Hermes-style ReAct agent loop for lead hunting."""

    def __init__(self) -> None:
        self.run_id = str(uuid.uuid4())
        self.iterations = 0
        self.max_iterations = config.AGENT_MAX_ITERATIONS
        self.history: list[dict[str, str]] = []
        self.leads_found: int = 0

    # ── LLM calls ─────────────────────────────────────────────────────────────

    def _call_ollama(self, messages: list[dict]) -> str:
        """Call local Ollama (primary LLM)."""
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{config.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": config.OLLAMA_MODEL,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.2, "num_predict": 2048},
                    },
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"]
        except Exception as e:
            logger.warning(f"Ollama unavailable: {e}")
            raise

    def _call_claude(self, messages: list[dict]) -> str:
        """Claude fallback (Anthropic US API)."""
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set - no fallback available")
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            # Convert messages format
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_messages = [m for m in messages if m["role"] != "system"]
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=2048,
                system=system_msg,
                messages=user_messages,
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude fallback also failed: {e}")
            raise

    def _llm(self, messages: list[dict]) -> str:
        """Try local first, fall back to Claude."""
        if config.USE_LOCAL_FIRST:
            try:
                return self._call_ollama(messages)
            except Exception:
                logger.info("Falling back to Claude API...")
        return self._call_claude(messages)

    # ── Parsing ────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_tag(text: str, tag: str) -> str | None:
        match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        return match.group(1).strip() if match else None

    @staticmethod
    def _parse_tool_call(text: str) -> dict | None:
        raw = HermesAgent._extract_tag(text, "tool_call")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse tool call JSON: {raw}")
            return None

    # ── Agent loop ─────────────────────────────────────────────────────────────

    def run(self, objective: str) -> str:
        """Run the Hermes ReAct loop until done or max iterations."""
        logger.info(f"[{self.run_id}] Starting agent. Objective: {objective}")

        tool_desc = "\n".join(
            f"- {t['name']}: {t['description']}" for t in TOOLS
        )
        system = SYSTEM_PROMPT.format(
            tool_descriptions=tool_desc,
            icp_threshold=config.ICP_SCORE_THRESHOLD,
        )

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": objective},
        ]

        while self.iterations < self.max_iterations:
            self.iterations += 1
            logger.info(f"[{self.run_id}] Iteration {self.iterations}")

            response = self._llm(messages)
            logger.debug(f"LLM response:\n{response}")

            messages.append({"role": "assistant", "content": response})

            # Check for final answer
            final = self._extract_tag(response, "final_answer")
            if final:
                logger.success(f"[{self.run_id}] Agent finished. Leads found: {self.leads_found}")
                return final

            # Parse and dispatch tool call
            tool_call = self._parse_tool_call(response)
            if not tool_call:
                logger.warning("No tool call found in response. Asking agent to continue.")
                messages.append({
                    "role": "user",
                    "content": "<observation>No tool was called. Please call a tool or provide a final_answer.</observation>",
                })
                continue

            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("arguments", {})
            logger.info(f"Tool call: {tool_name}({tool_args})")

            observation = dispatch_tool(tool_name, tool_args)
            if "leads_saved" in observation:
                # Track lead count from save_lead tool responses
                try:
                    obs_data = json.loads(observation)
                    self.leads_found += obs_data.get("leads_saved", 0)
                except Exception:
                    pass

            obs_msg = f"<observation>{observation}</observation>"
            messages.append({"role": "user", "content": obs_msg})
            logger.debug(f"Observation: {observation[:200]}...")

        return f"Max iterations ({self.max_iterations}) reached. Leads found: {self.leads_found}"
