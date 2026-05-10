"""Render a trajectory replay viewer as a standalone HTML file."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, "v2")
from agent.trajectory import load_trajectory


def render(path: str, out: str) -> str:
    run = load_trajectory(path)
    rows: list[str] = []
    for step in run.steps:
        rows.append(
            "<tr>"
            f"<td>{step.index}</td>"
            f"<td>{html.escape(step.kind)}</td>"
            f"<td>{html.escape(step.provider)}</td>"
            f"<td>{html.escape(step.tool_name)}</td>"
            f"<td>{step.latency_ms}</td>"
            f"<td><pre>{html.escape((step.message or '')[:240])}</pre></td>"
            "</tr>"
        )
    body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Hermes Replay Viewer</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; }}
    th {{ background: #f4f4f4; text-align: left; }}
    pre {{ margin: 0; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>Hermes Replay Viewer</h1>
  <p><b>Run ID:</b> {html.escape(run.run_id)}<br/>
     <b>Objective:</b> {html.escape(run.objective)}<br/>
     <b>Created:</b> {html.escape(run.created_at)}</p>
  <h2>Evaluation</h2>
  <pre>{html.escape(json.dumps(run.evaluation, indent=2, ensure_ascii=True))}</pre>
  <h2>Steps</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Kind</th><th>Provider</th><th>Tool</th><th>Latency ms</th><th>Message</th></tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HTML replay viewer for a trajectory")
    parser.add_argument("--path", required=True, help="Trajectory JSON path")
    parser.add_argument("--out", default="v2/reports/replay_view.html", help="Output HTML path")
    args = parser.parse_args()
    output = render(args.path, args.out)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

