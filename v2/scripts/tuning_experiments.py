"""Explicit, reviewable tuning experiments for Hermes routing and thresholds."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Variant:
    name: str
    env: dict[str, str]


def run_eval_with_env(variant: Variant) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(variant.env)
    proc = subprocess.run(
        ["python", "v2/evals/harness.py"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return {
        "name": variant.name,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "passed": proc.returncode == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run explicit tuning experiments")
    parser.add_argument("--out", default="v2/evals/experiment_results.json", help="Output report path")
    args = parser.parse_args()

    variants = [
        Variant("baseline", {}),
        Variant("tight_evidence", {"MIN_EVIDENCE_SCORE": "55"}),
        Variant("wider_discovery", {"MIN_DISCOVERY_RESULTS": "12"}),
    ]
    results = [run_eval_with_env(variant) for variant in variants]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"results": results}, indent=2))
    raise SystemExit(0 if all(item["passed"] for item in results) else 1)


if __name__ == "__main__":
    main()
