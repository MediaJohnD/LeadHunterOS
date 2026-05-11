"""24/7 watchdog cycle with heartbeat metrics and error-budget checks."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--error-budget", type=float, default=0.2, help="Max failed-run ratio.")
    parser.add_argument("--out", default="v2/evals/watchdog_heartbeat.json")
    args = parser.parse_args()

    results: list[dict[str, object]] = []
    failed = 0
    total_saved = 0
    for idx in range(1, args.cycles + 1):
        proc = subprocess.run(
            ["python", "v2/run_agent.py", "--strict-pass", "--objective", "Find and save qualified US SMB leads with deterministic pipeline."],
            check=False,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        if not ok:
            failed += 1
        out = (proc.stdout or "") + (proc.stderr or "")
        saved = 0
        marker = "'leads_saved': "
        pos = out.rfind(marker)
        if pos != -1:
            tail = out[pos + len(marker) : pos + len(marker) + 4]
            digits = "".join(ch for ch in tail if ch.isdigit())
            if digits:
                saved = int(digits)
        total_saved += saved
        results.append({"cycle": idx, "ok": ok, "saved": saved})

    success_rate = (args.cycles - failed) / max(1, args.cycles)
    avg_saved = total_saved / max(1, args.cycles)
    external_call_cost_estimate = 0.0  # no paid adapters by default
    payload = {
        "generated_at": _now(),
        "cycles": args.cycles,
        "success_rate": success_rate,
        "avg_saved_per_run": avg_saved,
        "external_call_cost_estimate": external_call_cost_estimate,
        "error_budget": args.error_budget,
        "error_budget_ok": (1 - success_rate) <= args.error_budget,
        "runs": results,
        "alerts": [] if (1 - success_rate) <= args.error_budget else ["error_budget_exceeded"],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["error_budget_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

