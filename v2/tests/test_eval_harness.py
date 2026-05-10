from __future__ import annotations

import sys
import unittest

sys.path.insert(0, "v2")

from evals.harness import run_all


class EvalHarnessTests(unittest.TestCase):
    def test_all_fixtures_pass(self) -> None:
        results = run_all()
        self.assertGreaterEqual(len(results), 3)
        failed = [r for r in results if not r.passed]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
