from __future__ import annotations

import os
import tempfile
import unittest
import sys

sys.path.insert(0, "v2")
from agent.telemetry import Telemetry


class TelemetryTests(unittest.TestCase):
    def test_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "telemetry.jsonl")
            t = Telemetry(path=path)
            t.emit(
                "test.event",
                trace_id="t",
                correlation_id="c",
                authorization="Bearer secret",
                api_key="abc",
                value="ok",
            )
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("[REDACTED]", content)
            self.assertNotIn("Bearer secret", content)

    def test_prom_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "telemetry.jsonl")
            t = Telemetry(path=path)
            t.emit("x", trace_id="t", correlation_id="c", latency_ms=10)
            out = t.export_prometheus()
            self.assertIn("hermes_events_total", out)
            self.assertIn("hermes_event_latency_ms_avg", out)


if __name__ == "__main__":
    unittest.main()
