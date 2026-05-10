"""LeadHunterOS v2 - True Hermes Agent."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

import config
from agent.database import record_tool_health_event
from agent.llm_router import LLMRouter
from agent.telemetry import telemetry
from agent.trajectory import TrajectoryRecorder, env_trajectory_enabled
from agent.tools import TOOLS, dispatch_tool, get_tool_schema_xml


def _build_system_prompt() -> str:
    """Build the Hermes system prompt from the live tool registry."""
    return f"""You are LeadHunterOS.
Rules:
1) Use public signals first, then enrichment, then ranking/orchestration.
2) US scope only: {config.TARGET_COUNTRY}; exclude unclear/non-US leads.
3) Never invent data. No placeholders.
4) Enforce SMB ICP hard filters before save/CRM handoff (titles, industries, company-size range).
5) Save only leads meeting gates: icp_score >= {config.ICP_MIN_SCORE}.
6) Outreach generation is disabled; prepare CRM handoff notes instead.
7) Max 3 tool calls per turn. Before FINAL ANSWER, run discovery -> rank_leads -> orchestrate_playbook.

Tool call format:
<tool_call>{{"name":"tool_name","arguments":{{...}}}}</tool_call>

Finish with:
FINAL ANSWER: concise summary + top leads + actions + gaps

Tools:
{get_tool_schema_xml()}"""


MAX_ITERATIONS = config.AGENT_MAX_ITERATIONS
_VALID_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in TOOLS)
_MAX_TOOL_CALLS_PER_TURN = 3
_DISCOVERY_TOOLS = {
    "search_signals",
    "search_jobs_public",
    "search_jobs_by_icp",
    "search_news_signals",
    "search_reddit_signals",
    "search_public_profiles",
}
_REQUIRED_PRE_FINAL_TOOLS = {"rank_leads", "orchestrate_playbook"}


class HermesAgent:
    """True Hermes agent with XML tool-calling and ReAct loop."""

    def __init__(
        self,
        preferred_backend: str | None = None,
        *,
        router: LLMRouter | None = None,
        tool_dispatcher: Any = None,
    ) -> None:
        self.router = router or LLMRouter(preferred_backend=preferred_backend)
        self.tool_dispatcher = tool_dispatcher or dispatch_tool
        self.session_id = str(uuid.uuid4())[:8]
        self.system_prompt = _build_system_prompt()
        self.trace_id, self.correlation_id = telemetry.new_trace()
        self.trajectory_recorder = TrajectoryRecorder(directory="v2/trajectories")
        self.capture_trajectory = env_trajectory_enabled()
        logger.info(
            f"HermesAgent initialized | session={self.session_id} "
            f"| backends={self.router.available_backends} | tools={len(TOOLS)}"
        )

    def run(self, objective: str) -> dict[str, Any]:
        """Run the full Hermes ReAct loop for the given objective."""
        logger.info(f"[{self.session_id}] Starting agent run")
        logger.info(f"[{self.session_id}] Objective: {objective[:120]}")
        telemetry.emit(
            "agent.run.start",
            trace_id=self.trace_id,
            correlation_id=self.correlation_id,
            session_id=self.session_id,
            objective=objective[:300],
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": objective},
        ]
        if self.capture_trajectory:
            self.trajectory_recorder.start(
                session_id=self.session_id,
                objective=objective,
                trace_id=self.trace_id,
                correlation_id=self.correlation_id,
                context={"max_iterations": MAX_ITERATIONS},
            )

        leads_saved: list[dict[str, Any]] = []
        iterations = 0
        last_response: dict[str, Any] = {}
        gate_reasons: list[str] = []
        run_timeline: list[dict[str, Any]] = []
        no_progress_turns = 0
        tool_result_cache: dict[str, dict[str, Any]] = {}
        tools_seen: set[str] = set()
        premature_finalizations = 0
        repeated_tool_counts: dict[str, int] = {}
        last_tool_names: list[str] = []

        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"[{self.session_id}] Iteration {iterations}/{MAX_ITERATIONS}")

            try:
                response = self.router.route(messages)
            except RuntimeError as exc:
                logger.error(f"[{self.session_id}] All backends failed: {exc}")
                telemetry.emit(
                    "agent.run.error",
                    level="ERROR",
                    trace_id=self.trace_id,
                    correlation_id=self.correlation_id,
                    session_id=self.session_id,
                    error=str(exc),
                )
                if self.capture_trajectory and self.trajectory_recorder.current:
                    self.trajectory_recorder.current.errors.append(str(exc))
                break

            last_response = response
            content = response["content"]
            logger.info(
                f"[{self.session_id}] Response from "
                f"{response['backend']}/{response['model']} ({len(content)} chars)"
            )
            telemetry.emit(
                "agent.iteration.response",
                trace_id=self.trace_id,
                correlation_id=self.correlation_id,
                session_id=self.session_id,
                iteration=iterations,
                provider=response.get("backend", ""),
                model=response.get("model", ""),
                latency_ms=response.get("latency_ms", 0),
                content_len=len(content),
            )
            run_timeline.append(
                {
                    "iteration": iterations,
                    "event": "provider_response",
                    "provider": response.get("backend", ""),
                    "model": response.get("model", ""),
                    "latency_ms": int(response.get("latency_ms", 0) or 0),
                    "content_len": len(content),
                }
            )
            if self.capture_trajectory:
                self.trajectory_recorder.add_step(
                    kind="provider_response",
                    provider=response.get("backend", ""),
                    model=response.get("model", ""),
                    message=content[:4000],
                    latency_ms=int(response.get("latency_ms", 0) or 0),
                )

            if "FINAL ANSWER:" in content:
                has_discovery = bool(tools_seen.intersection(_DISCOVERY_TOOLS))
                missing_required = sorted(t for t in _REQUIRED_PRE_FINAL_TOOLS if t not in tools_seen)
                if not has_discovery or missing_required:
                    premature_finalizations += 1
                    gate_reason = (
                        "final_answer_blocked:"
                        f"has_discovery={has_discovery},missing_required={','.join(missing_required) or 'none'}"
                    )
                    gate_reasons.append(gate_reason)
                    run_timeline.append(
                        {
                            "iteration": iterations,
                            "event": "gate_block",
                            "reason": gate_reason,
                            "kind": "premature_final_answer",
                        }
                    )
                    logger.warning(
                        f"[{self.session_id}] Premature FINAL ANSWER blocked "
                        f"(has_discovery={has_discovery}, missing={missing_required})"
                    )
                    messages.append({"role": "assistant", "content": self._assistant_history_entry(content, [])})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Do not finalize yet. Before FINAL ANSWER, run at least one discovery tool "
                            f"({', '.join(sorted(_DISCOVERY_TOOLS))}) and run both required tools: "
                            "rank_leads and orchestrate_playbook. Then finalize."
                        ),
                    })
                    if premature_finalizations >= 2:
                        messages.append({
                            "role": "user",
                            "content": (
                                "Use exactly two tool calls now: "
                                "1) rank_leads on current candidates, "
                                "2) orchestrate_playbook on ranked candidates. "
                                "Then return FINAL ANSWER."
                            ),
                        })
                    continue
                messages.append({"role": "assistant", "content": content})
                logger.success(f"[{self.session_id}] Agent reached final answer")
                telemetry.emit(
                    "agent.run.final_answer",
                    trace_id=self.trace_id,
                    correlation_id=self.correlation_id,
                    session_id=self.session_id,
                    iteration=iterations,
                )
                run_timeline.append(
                    {
                        "iteration": iterations,
                        "event": "final_answer",
                    }
                )
                break

            tool_calls, parse_errors = self._parse_tool_calls(content)
            messages.append({"role": "assistant", "content": self._assistant_history_entry(content, tool_calls)})
            if not tool_calls and not parse_errors:
                no_progress_turns += 1
                logger.warning(f"[{self.session_id}] No tool call or final answer. Nudging.")
                telemetry.emit(
                    "agent.iteration.no_progress",
                    level="WARNING",
                    trace_id=self.trace_id,
                    correlation_id=self.correlation_id,
                    session_id=self.session_id,
                    iteration=iterations,
                    no_progress_turns=no_progress_turns,
                )
                if no_progress_turns >= max(1, int(getattr(config, "AUTO_REPAIR_NO_PROGRESS_LIMIT", 2))):
                    gate_reason = (
                        "auto_repair_no_progress:"
                        f"no_progress_turns={no_progress_turns}"
                    )
                    gate_reasons.append(gate_reason)
                    run_timeline.append(
                        {
                            "iteration": iterations,
                            "event": "gate_block",
                            "reason": gate_reason,
                            "kind": "no_progress",
                        }
                    )
                    messages.append({
                        "role": "user",
                        "content": (
                            "No valid tool calls detected repeatedly. "
                            "Use exactly two tool calls now: search_signals then rank_leads. "
                            "If no candidates, return FINAL ANSWER with explicit blocker list."
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
                tools_seen.add(tool_name)
                run_timeline.append(
                    {
                        "iteration": iterations,
                        "event": "tool_called",
                        "tool_name": tool_name,
                    }
                )
                repeated_tool_counts[tool_name] = repeated_tool_counts.get(tool_name, 0) + 1
                last_tool_names.append(tool_name)
                if len(last_tool_names) > 10:
                    last_tool_names = last_tool_names[-10:]

                if repeated_tool_counts[tool_name] > max(1, int(getattr(config, "AUTO_REPAIR_REPEAT_TOOL_LIMIT", 3))):
                    gate_reason = (
                        "auto_repair_repeat_tool:"
                        f"tool={tool_name},count={repeated_tool_counts[tool_name]}"
                    )
                    gate_reasons.append(gate_reason)
                    run_timeline.append(
                        {
                            "iteration": iterations,
                            "event": "gate_block",
                            "reason": gate_reason,
                            "kind": "repeat_tool",
                        }
                    )
                    result = {
                        "ok": False,
                        "error": (
                            f"Auto-repair guard: tool '{tool_name}' exceeded repeat limit. "
                            "Switch to a different discovery or ranking tool."
                        ),
                    }
                    tool_responses.append(
                        f"<tool_response>\n"
                        f"Tool: {tool_name}\n"
                        f"Result: {json.dumps(result, separators=(',', ':'), default=str)}\n"
                        f"</tool_response>"
                    )
                    continue

                if tool_name not in _VALID_TOOL_NAMES:
                    result: dict[str, Any] = {
                        "ok": False,
                        "error": f"Unknown tool: {tool_name}",
                        "available_tools": sorted(_VALID_TOOL_NAMES),
                    }
                else:
                    try:
                        cache_key = ""
                        if tool_name in {"score_lead", "rank_leads", "orchestrate_playbook"}:
                            cache_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, default=str)}"
                        if cache_key and cache_key in tool_result_cache:
                            result = tool_result_cache[cache_key]
                            result = dict(result)
                            result["cache_hit"] = True
                        else:
                            result = self.tool_dispatcher(tool_name, tool_args)
                            if cache_key:
                                tool_result_cache[cache_key] = dict(result)
                        telemetry.emit(
                            "agent.tool.result",
                            trace_id=self.trace_id,
                            correlation_id=self.correlation_id,
                            session_id=self.session_id,
                            iteration=iterations,
                            tool_name=tool_name,
                            ok=bool(result.get("ok", False)),
                            cache_hit=bool(result.get("cache_hit", False)),
                        )
                        if self.capture_trajectory:
                            self.trajectory_recorder.add_step(
                                kind="tool_result",
                                tool_name=tool_name,
                                tool_args=tool_args,
                                tool_result=self._compact_tool_result(result),
                            )
                        record_tool_health_event(
                            component="tool_dispatch",
                            tool_name=tool_name,
                            source_name=str(tool_args.get("source_type", "")),
                            ok=bool(result.get("ok", False)),
                            error_text=str(result.get("error", "")) if not result.get("ok", True) else "",
                            context={"session_id": self.session_id, "iteration": iterations},
                        )
                        if tool_name == "save_lead" and result.get("saved"):
                            leads_saved.append(result.get("lead", result))
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc), "tool": tool_name}
                        telemetry.emit(
                            "agent.tool.exception",
                            level="WARNING",
                            trace_id=self.trace_id,
                            correlation_id=self.correlation_id,
                            session_id=self.session_id,
                            iteration=iterations,
                            tool_name=tool_name,
                            error=str(exc),
                        )
                        record_tool_health_event(
                            component="tool_dispatch",
                            tool_name=tool_name,
                            ok=False,
                            error_text=str(exc),
                            context={"session_id": self.session_id, "iteration": iterations},
                        )
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

            # Auto-repair escalation: if we are looping without meaningful progression, force shortest gate path.
            if iterations >= 3 and len(last_tool_names) >= 6:
                recent = last_tool_names[-6:]
                if len(set(recent)) <= 2:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Auto-repair mode: avoid repeating recent tools. "
                            "Run rank_leads on current candidates, then orchestrate_playbook, then FINAL ANSWER."
                        ),
                    })

        if iterations >= MAX_ITERATIONS:
            logger.warning(f"[{self.session_id}] Hit max iterations ({MAX_ITERATIONS})")
            telemetry.emit(
                "agent.run.max_iterations",
                level="WARNING",
                trace_id=self.trace_id,
                correlation_id=self.correlation_id,
                session_id=self.session_id,
                max_iterations=MAX_ITERATIONS,
            )

        result_payload = {
            "session_id": self.session_id,
            "objective": objective,
            "iterations": iterations,
            "leads_saved": len(leads_saved),
            "leads": leads_saved,
            "backend_used": last_response.get("backend", "none"),
            "model_used": last_response.get("model", "none"),
            "gate_reasons": gate_reasons,
            "timeline": run_timeline,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.capture_trajectory:
            path = self.trajectory_recorder.finish(
                final_response=last_response.get("content", ""),
                final_result=result_payload,
                evaluation={"leads_saved": len(leads_saved), "iterations": iterations},
            )
            result_payload["trajectory_path"] = path
        telemetry.emit(
            "agent.run.complete",
            trace_id=self.trace_id,
            correlation_id=self.correlation_id,
            session_id=self.session_id,
            iterations=iterations,
            leads_saved=len(leads_saved),
            backend_used=result_payload["backend_used"],
            model_used=result_payload["model_used"],
        )
        return result_payload

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
