"""Generate a morning digest (Markdown + JSON) from persisted leads."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="leadhunter.db")
    parser.add_argument("--hot-limit", type=int, default=10)
    parser.add_argument("--warm-limit", type=int, default=100)
    parser.add_argument("--out-md", default="reports/morning_digest.md")
    parser.add_argument("--out-json", default="reports/morning_digest.json")
    parser.add_argument("--hot-min-icp", type=int, default=80)
    parser.add_argument("--warm-min-icp", type=int, default=70)
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, full_name, title, company_name, company_domain, icp_score, status,
               signal_summary, decision_reason, created_at
        FROM leads
        ORDER BY datetime(created_at) DESC
        LIMIT 1000
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()

    hot = [r for r in rows if int(r.get("icp_score", 0) or 0) >= args.hot_min_icp][: args.hot_limit]
    warm = [r for r in rows if args.warm_min_icp <= int(r.get("icp_score", 0) or 0) < args.hot_min_icp][: args.warm_limit]

    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    md_lines = [
        f"# LeadHunterOS Morning Digest ({_now()})",
        "",
        f"- HOT leads: {len(hot)}",
        f"- WARM leads: {len(warm)}",
        "",
        "## HOT",
    ]
    for idx, row in enumerate(hot, start=1):
        why = row.get("decision_reason") or row.get("signal_summary") or "No reason recorded."
        md_lines.extend(
            [
                f"{idx}. **{row.get('company_name','')}** — {row.get('full_name','')} ({row.get('title','')})",
                f"   - ICP: {row.get('icp_score',0)}",
                f"   - Domain: {row.get('company_domain','')}",
                f"   - Why now: {why}",
            ]
        )
    md_lines.append("")
    md_lines.append("## WARM")
    for idx, row in enumerate(warm, start=1):
        md_lines.append(f"{idx}. {row.get('company_name','')} — ICP {row.get('icp_score',0)}")

    Path(args.out_md).write_text("\n".join(md_lines), encoding="utf-8")
    Path(args.out_json).write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "hot_count": len(hot),
                "warm_count": len(warm),
                "hot": hot,
                "warm": warm,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {args.out_md} and {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

