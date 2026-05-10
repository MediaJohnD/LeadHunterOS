"""CI/local regression gate runner."""

from __future__ import annotations

import subprocess


def run(command: list[str]) -> int:
    proc = subprocess.run(command, check=False)
    return proc.returncode


def main() -> int:
    commands = [
        ["python", "-m", "py_compile", "v2/config.py", "v2/run_agent.py", "v2/agent/hermes_agent.py", "v2/agent/llm_router.py", "v2/agent/tools.py", "v2/agent/database.py"],
        ["python", "-m", "unittest", "discover", "-s", "v2/tests", "-p", "test_*.py", "-q"],
        ["python", "v2/evals/harness.py"],
        ["python", "v2/scripts/run_beat_field_gate.py"],
    ]
    for cmd in commands:
        rc = run(cmd)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
