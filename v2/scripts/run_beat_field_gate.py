"""Beat-the-field release gate.

Runs:
1) unit/regression tests
2) eval harness
3) 10x/day stress simulation (10 eval passes)
4) writes scoreboard JSON

Exit non-zero when scoreboard is not green.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("v2")
SCOREBOARD_PATH = ROOT / "evals" / "beat_field_scoreboard.json"


def _run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output


def _eval_passed(output: str) -> bool:
    return "Summary:" in output and "passed" in output and "/6 passed" in output


def main() -> int:
    results: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "thresholds": {
            "unit_tests_must_pass": True,
            "eval_harness_must_pass": True,
            "stress_runs_min_pass_rate": 0.9,
        },
    }

    rc_tests, out_tests = _run(["python", "-m", "unittest", "discover", "-s", "v2/tests", "-p", "test_*.py", "-q"])
    results["checks"]["unit_tests"] = {"ok": rc_tests == 0}

    rc_eval, out_eval = _run(["python", "v2/evals/harness.py"])
    eval_ok = rc_eval == 0 and _eval_passed(out_eval)
    results["checks"]["eval_harness"] = {"ok": eval_ok}

    stress_pass = 0
    stress_runs = 10
    stress_details: list[dict[str, object]] = []
    for i in range(stress_runs):
        rc, out = _run(["python", "v2/evals/harness.py"])
        ok = rc == 0 and _eval_passed(out)
        if ok:
            stress_pass += 1
        stress_details.append({"run": i + 1, "ok": ok})
    pass_rate = stress_pass / stress_runs
    results["checks"]["stress_10x"] = {
        "ok": pass_rate >= 0.9,
        "pass_rate": pass_rate,
        "pass_count": stress_pass,
        "run_count": stress_runs,
        "runs": stress_details,
    }

    release_green = bool(
        results["checks"]["unit_tests"]["ok"]
        and results["checks"]["eval_harness"]["ok"]
        and results["checks"]["stress_10x"]["ok"]
    )
    results["release_green"] = release_green

    SCOREBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCOREBOARD_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0 if release_green else 1


if __name__ == "__main__":
    raise SystemExit(main())

