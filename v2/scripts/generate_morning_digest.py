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

    cur.execute(
        """
        SELECT company_name, signal_count, budget_score, urgency_score, evidence_summary, created_at
        FROM verified_leads
        WHERE budget_score >= 70 AND urgency_score >= 70
        ORDER BY datetime(created_at) DESC
        LIMIT :limit
        """,
        {"limit": max(1, int(args.hot_limit))},
    )
    verified_hot = [dict(r) for r in cur.fetchall()]
    con.close()

    hot: list[dict] = []
    for v in verified_hot:
        match = next(
            (r for r in rows if str(r.get("company_name", "")).strip().lower() == str(v.get("company_name", "")).strip().lower()),
            None,
        )
        if not match:
            continue
        hot.append(
            {
                **match,
                "signal_count": int(v.get("signal_count", 0) or 0),
                "budget_score": float(v.get("budget_score", 0) or 0),
                "urgency_score": float(v.get("urgency_score", 0) or 0),
                "evidence_summary": v.get("evidence_summary", ""),
            }
        )
        if len(hot) >= args.hot_limit:
            break

    hot_companies = {str(h.get("company_name", "")).strip().lower() for h in hot}
    warm_seen: set[str] = set()
    warm: list[dict] = []
    for r in rows:
        company = str(r.get("company_name", "")).strip().lower()
        if not company or company in hot_companies or company in warm_seen:
            continue
        if int(r.get("icp_score", 0) or 0) < args.warm_min_icp:
            continue
        warm_seen.add(company)
        warm.append(r)
        if len(warm) >= args.warm_limit:
            break
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
                f"{idx}. **{row.get('company_name','')}** - {row.get('full_name','')} ({row.get('title','')})",
                f"   - ICP: {row.get('icp_score',0)}",
                f"   - Domain: {row.get('company_domain','')}",
                f"   - Budget/Urgency: {row.get('budget_score', 0):.0f}/{row.get('urgency_score', 0):.0f}",
                f"   - Why now: {row.get('evidence_summary') or why}",
            ]
        )
    md_lines.append("")
    md_lines.append("## WARM")
    for idx, row in enumerate(warm, start=1):
        md_lines.append(f"{idx}. {row.get('company_name','')} - ICP {row.get('icp_score',0)}")

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
