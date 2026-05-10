"""Replay helpers for saved Hermes trajectories."""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "v2")
from agent.trajectory import diff_trajectories, load_trajectory, replay_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay and diff Hermes trajectories")
    parser.add_argument("--path", required=True, help="Trajectory JSON path")
    parser.add_argument("--compare", default="", help="Optional second trajectory to diff against")
    args = parser.parse_args()

    summary = replay_summary(args.path)
    print(json.dumps({"summary": summary}, indent=2))
    if args.compare:
        left = load_trajectory(args.path)
        right = load_trajectory(args.compare)
        print(json.dumps({"diff": diff_trajectories(left, right)}, indent=2))


if __name__ == "__main__":
    main()
