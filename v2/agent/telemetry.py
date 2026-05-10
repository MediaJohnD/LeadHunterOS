"""Structured telemetry for Hermes agent runtime."""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value.lower()
        if "api_key" in lowered or "authorization" in lowered or "bearer " in lowered:
            return "[REDACTED]"
        if len(value) > 400:
            return value[:400] + "...[truncated]"
        return value
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            if any(token in k.lower() for token in ("api_key", "authorization", "token", "secret", "password")):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_value(v)
        return redacted
    if isinstance(value, list):
        return [_redact_value(v) for v in value[:20]]
    return value


@dataclass
class TelemetryEvent:
    name: str
    level: str
    trace_id: str
    correlation_id: str
    observed_at: str
    fields: dict[str, Any] = field(default_factory=dict)


class Telemetry:
    """Lightweight structured telemetry sink.

    Produces JSONL events and in-memory dashboard-ready counters/histograms.
    """

    def __init__(self, path: str = "telemetry.jsonl") -> None:
        self.path = path
        self.enabled = _env_bool("TELEMETRY_ENABLED", True)
        self.redact = _env_bool("TELEMETRY_REDACT", True)
        self.sample_rate = float(os.getenv("TELEMETRY_SAMPLE_RATE", "1.0") or "1.0")
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._latency_totals: dict[str, int] = defaultdict(int)
        self._latency_counts: dict[str, int] = defaultdict(int)

    def new_trace(self) -> tuple[str, str]:
        return str(uuid.uuid4()), str(uuid.uuid4())

    def emit(self, name: str, level: str = "INFO", **fields: Any) -> None:
        if not self.enabled:
            return
        event = TelemetryEvent(
            name=name,
            level=level,
            trace_id=str(fields.pop("trace_id", "")),
            correlation_id=str(fields.pop("correlation_id", "")),
            observed_at=datetime.now(timezone.utc).isoformat(),
            fields=fields,
        )
        payload = {
            "name": event.name,
            "level": event.level,
            "trace_id": event.trace_id,
            "correlation_id": event.correlation_id,
            "observed_at": event.observed_at,
            "fields": _redact_value(event.fields) if self.redact else event.fields,
        }
        line = json.dumps(payload, ensure_ascii=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._counters[name] += 1
            latency = payload.get("fields", {}).get("latency_ms")
            if isinstance(latency, (int, float)):
                self._latency_totals[name] += int(latency)
                self._latency_counts[name] += 1

    def export_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, count in sorted(self._counters.items()):
                metric_name = f"hermes_events_total{{event=\"{name}\"}}"
                lines.append(f"{metric_name} {count}")
            for name, total in sorted(self._latency_totals.items()):
                cnt = max(1, self._latency_counts.get(name, 1))
                avg = total / cnt
                lines.append(f"hermes_event_latency_ms_avg{{event=\"{name}\"}} {avg:.2f}")
        return "\n".join(lines) + ("\n" if lines else "")


telemetry = Telemetry()
