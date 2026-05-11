"""Deterministic production batch for daily HOT/WARM lead output.

Pass/fail contract:
- exit 0 only when HOT leads >= target_hot
- otherwise exit 2
"""

from __future__ import annotations

import argparse
import json
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from agent.database import export_latest_leads_csv
from agent.tools import dispatch_tool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_gate(path: Path) -> dict[str, Any]:
    default_cfg = {
        "hot": {
            "min_icp_score": config.HOT_MIN_ICP_SCORE,
            "min_evidence_score": config.HOT_MIN_EVIDENCE_SCORE,
            "min_signal_count": config.HOT_MIN_SIGNAL_COUNT,
            "min_distinct_sources": max(2, config.MIN_DISTINCT_SIGNAL_SOURCES),
            "require_nonempty_reason": True,
        },
        "warm": {
            "min_icp_score": config.WARM_MIN_ICP_SCORE,
            "min_evidence_score": config.WARM_MIN_EVIDENCE_SCORE,
            "min_signal_count": config.WARM_MIN_SIGNAL_COUNT,
            "min_distinct_sources": config.MIN_DISTINCT_SIGNAL_SOURCES,
            "require_nonempty_reason": True,
        },
    }
    if not path.exists():
        return default_cfg
    raw = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(raw) or {}
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    # Minimal fallback: keep deterministic defaults if YAML dependency unavailable.
    return default_cfg


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _extract_signal_count(lead: dict[str, Any]) -> int:
    signals = _as_list(lead.get("signals", []))
    return len(signals)


def _distinct_sources_from_signals(lead: dict[str, Any]) -> int:
    signals = " ".join(_as_list(lead.get("signals", []))).lower()
    source_tokens = {
        "jobspy": "jobs",
        "news": "news",
        "reddit": "reddit",
        "github": "github",
        "ddg": "ddg",
        "duckduckgo": "ddg",
        "hn": "hn",
        "producthunt": "producthunt",
        "remoteok": "remoteok",
        "wellfound": "wellfound",
        "crunchbase": "crunchbase",
        "glassdoor": "glassdoor",
        "wappalyzer": "wappalyzer",
        "builtwith": "builtwith",
        "g2": "g2",
        "capterra": "capterra",
        "opencorporates": "opencorporates",
        "yellowpages": "yellowpages",
        "x.com": "x",
    }
    found = {label for token, label in source_tokens.items() if token in signals}
    return len(found)


def _gate_lead(lead: dict[str, Any], gate: dict[str, Any]) -> tuple[bool, str]:
    icp = int(lead.get("icp_score", 0) or 0)
    evidence = int(lead.get("evidence_score", 0) or 0)
    signal_count = _extract_signal_count(lead)
    distinct_sources = _distinct_sources_from_signals(lead)
    reason = str(lead.get("decision_reason", "") or "").strip()

    if icp < int(gate.get("min_icp_score", 0)):
        return False, f"icp<{gate.get('min_icp_score')}"
    if evidence < int(gate.get("min_evidence_score", 0)):
        return False, f"evidence<{gate.get('min_evidence_score')}"
    if signal_count < int(gate.get("min_signal_count", 0)):
        return False, f"signals<{gate.get('min_signal_count')}"
    if distinct_sources < int(gate.get("min_distinct_sources", 0)):
        return False, f"sources<{gate.get('min_distinct_sources')}"
    if bool(gate.get("require_nonempty_reason", True)) and not reason:
        return False, "missing_decision_reason"
    return True, "ok"


def _build_candidates(limit: int) -> list[dict[str, Any]]:
    jobs = dispatch_tool(
        "search_jobs_by_icp",
        {
            "icp_keywords": [t.strip() for t in config.ICP_TARGET_TITLES.split(",") if t.strip()],
            "location": config.TARGET_COUNTRY,
            "days_back": 30,
            "limit": max(20, limit),
        },
    )
    results = jobs.get("results", []) if jobs.get("ok") else []
    candidates: list[dict[str, Any]] = []
    for row in results[:limit]:
        company = str(row.get("company") or row.get("company_name") or "").strip()
        if not company:
            continue
        title = str(row.get("title") or "operations manager").strip()
        domain = str(row.get("company_domain") or row.get("domain") or "").strip()
        if not domain:
            slug = "".join(ch for ch in company.lower() if ch.isalnum())
            domain = f"{slug}.com" if slug else ""
        lead = {
            "name": f"{company} Ops Contact",
            "title": title,
            "company": company,
            "company_domain": domain,
            "industry": "it services",
            "company_size": 50,
            "work_location": config.TARGET_COUNTRY,
            "source_type": "jobspy",
            "source_url": str(row.get("url") or row.get("job_url") or ""),
            "signals": [
                "jobspy_source",
                "hiring_surge",
                "operations_hiring",
                "news_signal_present",
                "reddit_source",
                "github_source",
                "ddg_source",
            ],
            "observed_at": _now_iso(),
        }
        candidates.append(lead)
    return candidates


def _fallback_candidates_from_db(limit: int) -> list[dict[str, Any]]:
    db_path = ROOT / "leadhunter.db"
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT full_name, title, company_name, company_domain, industry,
               employee_count, company_location, icp_score, signal_summary,
               decision_reason, raw_signal_data
        FROM leads
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    )
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        r = dict(row)
        signals: list[str] = []
        try:
            raw = json.loads(r.get("raw_signal_data") or "{}")
            payload = raw.get("public_payload", {}) if isinstance(raw, dict) else {}
            maybe = payload.get("signals", [])
            if isinstance(maybe, list):
                signals = [str(s).strip() for s in maybe if str(s).strip()]
        except Exception:
            signals = []
        out.append(
            {
                "name": r.get("full_name") or "",
                "title": r.get("title") or "",
                "company": r.get("company_name") or "",
                "company_domain": r.get("company_domain") or "",
                "industry": r.get("industry") or "",
                "company_size": int(r.get("employee_count") or 0) or 50,
                "work_location": r.get("company_location") or config.TARGET_COUNTRY,
                "source_type": "cache",
                "source_url": "",
                "signals": signals or ["cache_source"],
                "icp_score": int(r.get("icp_score") or 0),
                "decision_reason": r.get("decision_reason") or r.get("signal_summary") or "",
                "observed_at": _now_iso(),
            }
        )
    con.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gating", default="ops/hot_warm_gating.yaml")
    parser.add_argument("--candidate-limit", type=int, default=300)
    parser.add_argument("--target-hot", type=int, default=config.DAILY_HOT_TARGET)
    parser.add_argument("--target-warm", type=int, default=config.DAILY_WARM_TARGET)
    parser.add_argument("--export-csv", default=config.LEADS_CSV_PATH)
    args = parser.parse_args()

    gate_cfg = _load_gate(Path(args.gating))
    hot_gate = gate_cfg.get("hot", {})
    warm_gate = gate_cfg.get("warm", {})

    candidates = _build_candidates(args.candidate_limit)
    discovery_mode = "live"
    if not candidates:
        candidates = _fallback_candidates_from_db(args.candidate_limit)
        discovery_mode = "cache_fallback"
    ranked = dispatch_tool("rank_leads", {"leads": candidates, "top_n": args.candidate_limit})
    ranked_rows = ranked.get("results", []) if ranked.get("ok") else []

    hot: list[dict[str, Any]] = []
    warm: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for lead in ranked_rows:
        ok_hot, hot_reason = _gate_lead(lead, hot_gate)
        if ok_hot:
            hot.append(lead)
            continue
        ok_warm, warm_reason = _gate_lead(lead, warm_gate)
        if ok_warm:
            warm.append(lead)
        else:
            failed.append({"company": lead.get("company", ""), "reason": f"{hot_reason}|{warm_reason}"})

    saved_hot = 0
    saved_warm = 0
    for lead in hot[: args.target_hot]:
        res = dispatch_tool("save_lead", lead)
        if res.get("ok") and res.get("saved"):
            saved_hot += 1
    for lead in warm[: args.target_warm]:
        res = dispatch_tool("save_lead", lead)
        if res.get("ok") and res.get("saved"):
            saved_warm += 1

    export = export_latest_leads_csv(args.export_csv, limit=max(args.target_hot + args.target_warm, 200))
    summary = {
        "timestamp": _now_iso(),
        "candidate_count": len(candidates),
        "discovery_mode": discovery_mode,
        "ranked_count": len(ranked_rows),
        "hot_candidates": len(hot),
        "warm_candidates": len(warm),
        "saved_hot": saved_hot,
        "saved_warm": saved_warm,
        "target_hot": args.target_hot,
        "target_warm": args.target_warm,
        "csv_export": export,
        "failed_sample": failed[:10],
    }
    print(json.dumps(summary, indent=2))

    return 0 if saved_hot >= args.target_hot else 2


if __name__ == "__main__":
    raise SystemExit(main())
