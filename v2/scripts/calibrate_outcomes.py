"""Outcome calibration helper.

Reads recent outcome_feedback and suggests score-weight direction changes.
"""

from __future__ import annotations

import sqlite3

DB_PATH = "leadhunter.db"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT outcome_type, COUNT(*), AVG(COALESCE(outcome_value,1))
        FROM outcome_feedback
        GROUP BY outcome_type
        ORDER BY COUNT(*) DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No outcome_feedback found. Collect CRM outcomes first.")
        return
    positive = {"reply", "meeting", "qualified", "converted"}
    negative = {"bounce", "unqualified", "spam", "rejected"}
    pos, neg = 0.0, 0.0
    for outcome_type, count, avg_value in rows:
        weight = float(count or 0) * float(avg_value or 0)
        if str(outcome_type).lower() in positive:
            pos += weight
        if str(outcome_type).lower() in negative:
            neg += weight
    print("Outcome calibration summary")
    print(f"positive_signal_weight={pos:.2f}")
    print(f"negative_signal_weight={neg:.2f}")
    if pos > neg:
        print("Recommendation: modestly increase intent/evidence weights.")
    elif neg > pos:
        print("Recommendation: tighten evidence and min distinct source gates.")
    else:
        print("Recommendation: keep weights stable; gather more data.")


if __name__ == "__main__":
    main()
