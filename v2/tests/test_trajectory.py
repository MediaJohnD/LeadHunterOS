from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, "v2")
from agent.trajectory import TrajectoryRecorder, diff_trajectories, load_trajectory, replay_summary


class TrajectoryTests(unittest.TestCase):
    def test_record_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rec = TrajectoryRecorder(directory=tmp)
            rec.start(
                session_id="s1",
                objective="obj",
                trace_id="t",
                correlation_id="c",
                context={},
            )
            rec.add_step(kind="tool_result", tool_name="search_signals", tool_result={"ok": True})
            path1 = rec.finish(final_response="FINAL ANSWER: ok", final_result={"ok": True}, evaluation={"score": 1})
            run1 = load_trajectory(path1)

            rec2 = TrajectoryRecorder(directory=tmp)
            rec2.start(
                session_id="s2",
                objective="obj",
                trace_id="t2",
                correlation_id="c2",
                context={},
            )
            rec2.add_step(kind="tool_result", tool_name="rank_leads", tool_result={"ok": True})
            path2 = rec2.finish(final_response="FINAL ANSWER: changed", final_result={"ok": True}, evaluation={"score": 1})
            run2 = load_trajectory(path2)
            d = diff_trajectories(run1, run2)
            self.assertTrue(d["tool_sequence_changed"])
            self.assertTrue(d["final_response_changed"])

    def test_golden_trajectory_regression(self) -> None:
        fixture = Path("v2/tests/fixtures/golden_trajectory_minimal.json")
        run = load_trajectory(str(fixture))
        summary = replay_summary(str(fixture))

        self.assertEqual(run.run_id, "golden-run-001")
        self.assertEqual(run.context.get("max_iterations"), 15)
        self.assertEqual(summary["steps"], 4)
        self.assertEqual(summary["providers"], ["local"])
        self.assertEqual(
            summary["tools"],
            ["search_signals", "rank_leads", "orchestrate_playbook"],
        )
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["evaluation"].get("leads_saved"), 1)
        self.assertIn("FINAL ANSWER:", run.final_response)


if __name__ == "__main__":
    unittest.main()
