"""Lightweight evaluation harness for LeadHunterOS quality trends.

Metrics:
  - qualified_leads_per_run
  - false_positive_proxy
  - evidence_density
  - zero_lead_run_rate
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

DB_PATH = "leadhunter.db"


@dataclass
class EvalMetrics:
    qualified_leads_per_run: float
    false_positive_proxy: float
    evidence_density: float
    zero_lead_run_rate: float


def compute_metrics(db_path: str = DB_PATH) -> EvalMetrics:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM leads")
    total = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM leads WHERE status='qualified'")
    qualified = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT AVG(COALESCE(icp_score,0)) FROM leads")
    avg_icp = float(cur.fetchone()[0] or 0.0)
    cur.execute("SELECT AVG(COALESCE(attribution_confidence,0)) FROM leads")
    avg_conf = float(cur.fetchone()[0] or 0.0)
    conn.close()

    qualified_rate = (qualified / total) if total else 0.0
    false_positive_proxy = max(0.0, 1.0 - min(1.0, avg_conf / 100.0))
    evidence_density = min(1.0, avg_conf / 100.0)
    zero_lead_run_rate = 1.0 if total == 0 else 0.0

    return EvalMetrics(
        qualified_leads_per_run=qualified_rate,
        false_positive_proxy=false_positive_proxy,
        evidence_density=evidence_density,
        zero_lead_run_rate=zero_lead_run_rate,
    )


def main() -> None:
    m = compute_metrics()
    print("Eval Metrics")
    print(f"qualified_leads_per_run={m.qualified_leads_per_run:.3f}")
    print(f"false_positive_proxy={m.false_positive_proxy:.3f}")
    print(f"evidence_density={m.evidence_density:.3f}")
    print(f"zero_lead_run_rate={m.zero_lead_run_rate:.3f}")


if __name__ == "__main__":
    main()
