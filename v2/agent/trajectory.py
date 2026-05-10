"""Trajectory schema, recorder, replay, and diff helpers."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TrajectoryStep:
    index: int
    kind: str
    observed_at: str
    provider: str = ""
    model: str = ""
    message: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrajectoryRun:
    run_id: str
    session_id: str
    created_at: str
    objective: str
    trace_id: str
    correlation_id: str
    context: dict[str, Any] = field(default_factory=dict)
    steps: list[TrajectoryStep] = field(default_factory=list)
    final_response: str = ""
    final_result: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    evaluation: dict[str, Any] = field(default_factory=dict)


class TrajectoryRecorder:
    def __init__(self, directory: str = "trajectories") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.current: TrajectoryRun | None = None

    def start(
        self,
        *,
        session_id: str,
        objective: str,
        trace_id: str,
        correlation_id: str,
        context: dict[str, Any] | None = None,
    ) -> TrajectoryRun:
        run = TrajectoryRun(
            run_id=str(uuid.uuid4()),
            session_id=session_id,
            created_at=utc_now(),
            objective=objective,
            trace_id=trace_id,
            correlation_id=correlation_id,
            context=context or {},
        )
        self.current = run
        return run

    def add_step(self, **kwargs: Any) -> None:
        if not self.current:
            return
        step = TrajectoryStep(
            index=len(self.current.steps) + 1,
            observed_at=utc_now(),
            **kwargs,
        )
        self.current.steps.append(step)

    def finish(self, final_response: str, final_result: dict[str, Any], evaluation: dict[str, Any] | None = None) -> str:
        if not self.current:
            raise RuntimeError("trajectory not started")
        self.current.final_response = final_response
        self.current.final_result = final_result
        if evaluation:
            self.current.evaluation = evaluation
        path = self.directory / f"{self.current.created_at[:10]}_{self.current.run_id}.json"
        payload = asdict(self.current)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
        self.current = None
        return str(path)


def load_trajectory(path: str) -> TrajectoryRun:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    steps = [TrajectoryStep(**step) for step in raw.get("steps", [])]
    return TrajectoryRun(
        run_id=raw["run_id"],
        session_id=raw["session_id"],
        created_at=raw["created_at"],
        objective=raw["objective"],
        trace_id=raw.get("trace_id", ""),
        correlation_id=raw.get("correlation_id", ""),
        context=raw.get("context", {}),
        steps=steps,
        final_response=raw.get("final_response", ""),
        final_result=raw.get("final_result", {}),
        errors=raw.get("errors", []),
        evaluation=raw.get("evaluation", {}),
    )


def diff_trajectories(old: TrajectoryRun, new: TrajectoryRun) -> dict[str, Any]:
    old_tools = [step.tool_name for step in old.steps if step.tool_name]
    new_tools = [step.tool_name for step in new.steps if step.tool_name]
    return {
        "old_step_count": len(old.steps),
        "new_step_count": len(new.steps),
        "old_tools": old_tools,
        "new_tools": new_tools,
        "tool_sequence_changed": old_tools != new_tools,
        "final_response_changed": old.final_response != new.final_response,
        "evaluation_changed": old.evaluation != new.evaluation,
    }


def replay_summary(path: str) -> dict[str, Any]:
    run = load_trajectory(path)
    return {
        "run_id": run.run_id,
        "objective": run.objective,
        "steps": len(run.steps),
        "providers": sorted({step.provider for step in run.steps if step.provider}),
        "tools": [step.tool_name for step in run.steps if step.tool_name],
        "errors": run.errors,
        "evaluation": run.evaluation,
    }


def list_trajectories(directory: str = "trajectories") -> list[str]:
    base = Path(directory)
    if not base.exists():
        return []
    return sorted(str(path) for path in base.glob("*.json"))


def env_trajectory_enabled() -> bool:
    return os.getenv("TRAJECTORY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
