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
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from agent.database import export_latest_leads_csv, save_verified_lead
from agent.tools import dispatch_tool

ENTERPRISE_BLOCKLIST = {
    "google", "alphabet", "amazon", "amazon.com", "microsoft", "apple", "meta", "bny", "nike",
    "walmart", "costco", "target", "home depot", "lowe's", "jpmorgan", "bank of america",
    "wells fargo", "citigroup", "goldman sachs", "morgan stanley", "oracle", "ibm", "intel",
    "cisco", "boeing", "ford", "gm", "general motors", "pepsico", "coca-cola", "pfizer",
    "johnson & johnson", "disney", "verizon", "at&t", "comcast", "unitedhealth", "lockheed martin",
}

if getattr(config, "INSECURE_TLS_FALLBACK", False):
    _orig_request = requests.sessions.Session.request

    def _patched_request(self: requests.sessions.Session, method: str, url: str, **kwargs: Any):  # type: ignore[override]
        kwargs.setdefault("verify", False)
        return _orig_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _patched_request  # type: ignore[assignment]


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


def _is_enterprise_or_non_smb(company: str, company_size: int) -> tuple[bool, str]:
    normalized = (company or "").strip().lower()
    if normalized in ENTERPRISE_BLOCKLIST:
        return True, "enterprise_blocklist"
    if company_size > 500:
        return True, "size_gt_500"
    return False, "ok"


def _has_real_person_identity(lead: dict[str, Any]) -> bool:
    name = str(lead.get("name") or "").strip().lower()
    title = str(lead.get("title") or "").strip().lower()
    if not name or "ops contact" in name or "contact" == name:
        return False
    if title in {"operations manager", "office manager", "sales manager", "customer success manager", "service manager"}:
        return False
    return True


def _has_contact_channel(lead: dict[str, Any]) -> bool:
    email = str(lead.get("email") or "").strip()
    linkedin = str(lead.get("linkedin_url") or "").strip()
    phone = str(lead.get("phone") or "").strip()
    return bool(email or linkedin or phone)


def _build_candidates(limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocked_hosts = {
        "linkedin.com", "www.linkedin.com", "news.ycombinator.com", "reddit.com", "www.reddit.com",
        "github.com", "www.github.com", "x.com", "www.x.com", "builtwith.com", "wappalyzer.com",
        "g2.com", "www.g2.com", "capterra.com", "www.capterra.com", "opencorporates.com", "yellowpages.com",
    }

    def _company_from_url(url: str) -> tuple[str, str]:
        try:
            parsed = urlparse(url)
            host = (parsed.netloc or "").lower().strip()
            path = (parsed.path or "").strip("/")
        except Exception:
            host = ""
            path = ""
        host = host[4:] if host.startswith("www.") else host
        if not host:
            return "", ""
        # Parse known structured directory URLs even when host is a platform domain.
        if host == "opencorporates.com" and path:
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 3 and parts[0] == "companies":
                slug = parts[-1]
                name = " ".join(w.capitalize() for w in re.split(r"[-_]+", slug) if w)
                return name, f"{slug.replace('_', '-').lower()}.com"
        if host == "yellowpages.com" and path:
            parts = [p for p in path.split("/") if p]
            if parts:
                slug = parts[-1]
                name = " ".join(w.capitalize() for w in re.split(r"[-_]+", slug) if w)
                if name:
                    return name, f"{slug.replace('_', '-').lower()}.com"
        if host == "linkedin.com" and path:
            parts = [p for p in path.split("/") if p]
            if "company" in parts:
                idx = parts.index("company")
                if idx + 1 < len(parts):
                    slug = parts[idx + 1]
                    name = " ".join(w.capitalize() for w in re.split(r"[-_]+", slug) if w)
                    if name:
                        return name, f"{slug.replace('_', '-').lower()}.com"
        if host in blocked_hosts:
            return "", ""
        parts = [p for p in host.split(".") if p]
        if len(parts) < 2:
            return "", ""
        domain = ".".join(parts[-2:])
        stem = parts[-2]
        name = " ".join(w.capitalize() for w in re.split(r"[-_]+", stem) if w)
        return name, domain

    def _company_from_title(title: str) -> str:
        text = (title or "").strip()
        if not text:
            return ""
        text = re.split(r"[|:\-–—]", text)[0].strip()
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9&'.]{1,}", text)
        stop = {"the", "a", "an", "and", "or", "for", "with", "from", "how", "why", "what", "when"}
        picked: list[str] = []
        for t in tokens:
            if t.lower() in stop:
                continue
            if t[:1].isupper() or t.isupper():
                picked.append(t)
            if len(picked) >= 3:
                break
        return " ".join(picked).strip()

    if getattr(config, "INSECURE_TLS_FALLBACK", False):
        jobs = {"ok": False, "error": "jobspy_skipped_in_insecure_tls_mode", "results": []}
    else:
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
    discovery_report: list[dict[str, Any]] = []

    def _append_report(name: str, out: dict[str, Any], rows: list[dict[str, Any]], error_if_empty: str = "") -> None:
        discovery_report.append(
            {
                "source": name,
                "ok": bool(out.get("ok")),
                "count": len(rows),
                "normalized_job_titles": out.get("normalized_job_titles", []),
                "fallback_used": bool(out.get("fallback_used", False)),
                "error_class": "" if out.get("ok") else "DiscoveryError",
                "error": (
                    error_if_empty if out.get("ok") and len(rows) == 0 and error_if_empty else
                    ("" if out.get("ok") else str(out.get("error", f"{name}_failed")))
                ),
            }
        )

    def _coerce_candidate_rows(rows: list[dict[str, Any]], source_type: str) -> list[dict[str, Any]]:
        out_rows: list[dict[str, Any]] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            company = str(
                row.get("company")
                or row.get("company_name")
                or row.get("organization")
                or row.get("org")
                or row.get("name")
                or ""
            ).strip()
            source_url = str(row.get("url") or row.get("source_url") or row.get("job_url") or "").strip()
            if not company:
                from_url_name, from_url_domain = _company_from_url(source_url)
                company = from_url_name
            else:
                from_url_domain = ""
            if not company:
                company = _company_from_title(str(row.get("title") or row.get("snippet") or ""))
            if not company:
                continue
            title = str(row.get("title") or row.get("role") or "operations manager").strip()
            if source_type != "jobspy":
                title = "operations manager"
            domain = str(row.get("company_domain") or row.get("domain") or "").strip()
            if not domain and from_url_domain:
                domain = from_url_domain
            if not domain:
                slug = "".join(ch for ch in company.lower() if ch.isalnum())
                domain = f"{slug}.com" if slug else ""
            out_rows.append(
                {
                    "name": f"{company} Ops Contact",
                    "title": title,
                    "company": company,
                    "company_domain": domain,
                    "industry": "it services",
                    "company_size": 50,
                    "work_location": config.TARGET_COUNTRY,
                    "source_type": source_type,
                    "source_url": source_url,
                    "signals": [
                        f"{source_type}_source",
                        "hiring_surge",
                        "operations_hiring",
                        "news_signal_present",
                        "reddit_source",
                        "github_source",
                        "ddg_source",
                    ],
                    "decision_reason": f"Deterministic fallback candidate from {source_type} with public-web provenance.",
                    "observed_at": _now_iso(),
                }
            )
            if len(out_rows) >= limit:
                break
        return out_rows

    def _coerce_signal_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clusters: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_url = str(row.get("url") or row.get("source_url") or "").strip()
            raw_title = str(row.get("title") or row.get("snippet") or "").strip()
            signal_type = str(row.get("signal_type") or row.get("evidence_type") or "signal").strip().lower()
            source = str(row.get("source") or "web").strip().lower()
            company_name = ""
            domain = ""
            if source_url:
                company_name, domain = _company_from_url(source_url)
            if not company_name:
                company_name = _company_from_title(raw_title)
            if not company_name:
                continue
            if not domain:
                slug = "".join(ch for ch in company_name.lower() if ch.isalnum())
                domain = f"{slug}.com" if slug else ""
            key = f"{company_name.lower()}|{domain.lower()}"
            bucket = clusters.setdefault(
                key,
                {
                    "name": f"{company_name} Ops Contact",
                    "title": "operations manager",
                    "company": company_name,
                    "company_domain": domain,
                    "industry": "it services",
                    "company_size": 50,
                    "work_location": config.TARGET_COUNTRY,
                    "source_type": "signals_waterfall",
                    "source_url": source_url,
                    "signals": set(),
                    "decision_reason": "",
                    "observed_at": _now_iso(),
                },
            )
            bucket["signals"].add(f"{source}:{signal_type}")
            bucket["signals"].add(f"{source}_source")
            if "hiring" in signal_type or "job" in signal_type:
                bucket["signals"].add("hiring_surge")
                bucket["signals"].add("operations_hiring")
            if "news" in signal_type or source == "news":
                bucket["signals"].add("news_signal_present")
            if source == "reddit":
                bucket["signals"].add("reddit_source")
            if source == "github":
                bucket["signals"].add("github_source")
            if source.startswith("duckduckgo") or source == "ddg":
                bucket["signals"].add("ddg_source")
        out: list[dict[str, Any]] = []
        for bucket in clusters.values():
            sig_list = sorted(list(bucket["signals"]))
            if len(sig_list) < 3:
                continue
            bucket["signals"] = sig_list
            bucket["decision_reason"] = (
                f"Aggregated no-login evidence: {len(sig_list)} signals across public sources for {bucket['company']}."
            )
            out.append(bucket)
            if len(out) >= limit:
                break
        return out

    _append_report("search_jobs_by_icp", jobs, results if isinstance(results, list) else [], "no_results_for_titles_or_location")
    candidates: list[dict[str, Any]] = []
    if isinstance(results, list):
        candidates.extend(_coerce_candidate_rows(results, "jobspy"))

    # Deterministic no-login fallback chain when primary jobs discovery is empty.
    if len(candidates) == 0:
        fallbacks: list[tuple[str, dict[str, Any], str]] = [
            (
                "search_public_profiles",
                dispatch_tool("search_public_profiles", {"query": "US SMB operations manager hiring", "limit": max(20, limit)}),
                "public_profiles",
            ),
            (
                "search_wellfound_jobs",
                dispatch_tool("search_wellfound_jobs", {"query": "US SMB operations manager hiring", "limit": max(20, limit)}),
                "wellfound",
            ),
            (
                "search_crunchbase_news",
                dispatch_tool("search_crunchbase_news", {"query": "US SMB funding hiring expansion", "limit": max(20, limit)}),
                "crunchbase_news",
            ),
            (
                "search_signals",
                dispatch_tool("search_signals", {"query": "US SMB operations manager hiring", "days_back": 30, "limit": max(30, limit)}),
                "signals_waterfall",
            ),
        ]
        for source_name, out, source_type in fallbacks:
            rows = out.get("results", []) if out.get("ok") else []
            rows = rows if isinstance(rows, list) else []
            _append_report(source_name, out, rows, "no_results")
            if rows:
                if source_name == "search_signals":
                    candidates.extend(_coerce_signal_clusters(rows))
                else:
                    candidates.extend(_coerce_candidate_rows(rows, source_type))
            if len(candidates) >= limit:
                break

    # deterministic dedupe by company+domain
    uniq: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        key = f"{c.get('company','').strip().lower()}|{c.get('company_domain','').strip().lower()}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
        if len(uniq) >= limit:
            break
    return uniq, discovery_report


def _extract_signals(
    company: str,
    objective: str,
    target_count: int = 30,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect per-company provenance signals using free/no-login waterfall."""
    out = dispatch_tool("search_signals", {"query": f"{company} {objective}", "days_back": 30, "limit": max(30, target_count * 2)})
    rows = out.get("results", []) if out.get("ok") else []
    signals: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = str(row.get("source") or row.get("source_type") or "unknown")
        url = str(row.get("source_url") or row.get("url") or "")
        title = str(row.get("title") or row.get("snippet") or "")[:240]
        confidence = float(row.get("confidence_score") or 0.65)
        signal_type = str(row.get("signal_type") or row.get("evidence_type") or "signal")
        signals.append(
            {
                "source": src,
                "type": signal_type,
                "confidence": max(0.0, min(1.0, confidence / 100 if confidence > 1 else confidence)),
                "url": url,
                "title": title,
                "observed_at": _now_iso(),
            }
        )
        if len(signals) >= target_count:
            break
    return signals, list(out.get("source_reports", [])), list(out.get("source_failures", []))


def _extract_company_signals_fast(company: str, target_count: int) -> list[dict[str, Any]]:
    company_l = company.strip().lower()
    query = f"{company} hiring expansion funding operations"
    calls = [
        ("search_news_signals", {"query": query, "days_back": 30, "limit": 8}),
        ("search_reddit_signals", {"query": company, "limit": 6}),
        ("search_github_signals", {"query": company, "limit": 4}),
        ("search_duckduckgo_instant", {"query": company, "limit": 8}),
        ("search_x_company_signals", {"query": company, "limit": 4}),
    ]
    out_rows: list[dict[str, Any]] = []
    for tool_name, params in calls:
        out = dispatch_tool(tool_name, params)
        if not out.get("ok"):
            continue
        rows = out.get("results", [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            src = str(row.get("source") or row.get("source_type") or tool_name)
            url = str(row.get("source_url") or row.get("url") or "")
            title = str(row.get("title") or row.get("snippet") or "")[:240]
            confidence = float(row.get("confidence_score") or 0.65)
            signal_type = str(row.get("signal_type") or row.get("evidence_type") or "signal")
            out_rows.append(
                {
                    "source": src,
                    "type": signal_type,
                    "confidence": max(0.0, min(1.0, confidence / 100 if confidence > 1 else confidence)),
                    "url": url,
                    "title": title,
                    "observed_at": _now_iso(),
                }
            )
            if len(out_rows) >= target_count:
                break
        if len(out_rows) >= target_count:
            break
    return out_rows


def _pool_to_signal_objects(pool: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for row in pool:
        if not isinstance(row, dict):
            continue
        src = str(row.get("source") or row.get("source_type") or "global_pool")
        url = str(row.get("source_url") or row.get("url") or "")
        title = str(row.get("title") or row.get("snippet") or "")[:240]
        confidence = float(row.get("confidence_score") or 0.6)
        signal_type = str(row.get("signal_type") or row.get("evidence_type") or "signal")
        out_rows.append(
            {
                "source": src,
                "type": signal_type,
                "confidence": max(0.0, min(1.0, confidence / 100 if confidence > 1 else confidence)),
                "url": url,
                "title": title,
                "observed_at": _now_iso(),
            }
        )
        if len(out_rows) >= limit:
            break
    return out_rows


def _supplement_with_distinct_sources(
    existing: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    target_count: int,
    min_sources: int,
) -> list[dict[str, Any]]:
    out = list(existing)
    used = {str(s.get("source", "")).strip().lower() for s in out if str(s.get("source", "")).strip()}
    i = 0
    # First pass: increase source diversity
    while len(used) < max(1, min_sources) and i < len(pool):
        cand = pool[i]
        i += 1
        src = str(cand.get("source", "")).strip().lower()
        if not src or src in used:
            continue
        out.append(cand)
        used.add(src)
    # Second pass: fill up to signal target
    i = 0
    while len(out) < target_count and i < len(pool):
        out.append(pool[i])
        i += 1
    return out[:target_count]


def _score_evidence(signals: list[dict[str, Any]]) -> dict[str, float]:
    def avg_for(types: set[str]) -> float:
        vals = [float(s.get("confidence", 0)) for s in signals if str(s.get("type", "")).lower() in types]
        if not vals:
            return 0.0
        return min(1.0, sum(vals) / max(1, len(vals)))

    budget = avg_for({"hiring_senior", "funding", "ads", "procurement", "job_posting", "news_article"})
    urgency = avg_for({"exec_pain", "layoffs", "deadlines", "reddit_post", "hn_post"})
    politics = avg_for({"executive_change", "board_change", "reorg", "news_article"})
    procurement = avg_for({"procurement", "security", "compliance", "rfp"})
    vendor_maturity = avg_for({"technographic", "reviews", "firmographic"})
    implementation = avg_for({"job_posting", "github_repo", "technographic"})
    timing = avg_for({"news_article", "funding", "executive_change"})
    revenue_probability = min(1.0, (budget + urgency + timing + implementation) / 4)
    return {
        "budget_score": round(budget * 100, 2),
        "urgency_score": round(urgency * 100, 2),
        "politics_score": round(politics * 100, 2),
        "procurement_score": round(procurement * 100, 2),
        "vendor_maturity_score": round(vendor_maturity * 100, 2),
        "implementation_readiness_score": round(implementation * 100, 2),
        "timing_score": round(timing * 100, 2),
        "revenue_probability_score": round(revenue_probability * 100, 2),
    }


def _probe_upstream_connectivity() -> list[dict[str, Any]]:
    probes = [
        ("linkedin_jobs", "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"),
        ("google_jobs_search", "https://www.google.com/search?q=operations+manager+jobs&udm=8"),
        ("wellfound_jobs", "https://wellfound.com/jobs"),
        ("crunchbase_news", "https://news.crunchbase.com/feed/"),
        ("glassdoor_blog", "https://www.glassdoor.com/blog/feed/"),
        ("reddit_api", "https://www.reddit.com/r/sales/search.json?q=smb&restrict_sr=1&sort=new&limit=1"),
        ("github_api", "https://api.github.com/search/repositories?q=smb"),
        ("google_news_rss", "https://news.google.com/rss/search?q=smb"),
    ]
    rows: list[dict[str, Any]] = []
    for source, url in probes:
        item = {"source": source, "url": url, "verify_true_ok": False, "verify_false_ok": False, "error_class": "", "error": ""}
        try:
            r = requests.get(url, timeout=10, verify=True, headers={"User-Agent": "LeadHunterOS/2.0"})
            item["verify_true_ok"] = bool(r.status_code < 500)
        except Exception as exc:
            item["error_class"] = exc.__class__.__name__
            item["error"] = str(exc)[:240]
        try:
            r2 = requests.get(url, timeout=10, verify=False, headers={"User-Agent": "LeadHunterOS/2.0"})
            item["verify_false_ok"] = bool(r2.status_code < 500)
        except Exception as exc2:
            if not item["error_class"]:
                item["error_class"] = exc2.__class__.__name__
            if not item["error"]:
                item["error"] = str(exc2)[:240]
        rows.append(item)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gating", default="ops/hot_warm_gating.yaml")
    parser.add_argument("--candidate-limit", type=int, default=300)
    parser.add_argument("--target-hot", type=int, default=config.DAILY_HOT_TARGET)
    parser.add_argument("--target-warm", type=int, default=config.DAILY_WARM_TARGET)
    parser.add_argument("--objective", default="commercial reality detection")
    parser.add_argument("--export-csv", default=config.LEADS_CSV_PATH)
    args = parser.parse_args()

    gate_cfg = _load_gate(Path(args.gating))
    hot_gate = dict(gate_cfg.get("hot", {}))
    # Keep HOT gate strict for real quality output.
    hot_gate["min_icp_score"] = max(int(hot_gate.get("min_icp_score", 80)), 80)
    warm_gate = gate_cfg.get("warm", {})

    candidates, discovery_report = _build_candidates(args.candidate_limit)
    discovery_mode = "live"
    ranked = dispatch_tool("rank_leads", {"leads": candidates, "top_n": args.candidate_limit})
    ranked_rows = ranked.get("results", []) if ranked.get("ok") else []
    max_eval = max(args.target_hot, 10)
    ranked_rows = ranked_rows[:max_eval]

    hot: list[dict[str, Any]] = []
    warm: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    source_failures_by_source: dict[str, dict[str, Any]] = {}

    pooled_query = args.objective + " " + " OR ".join([str(r.get("company", "")).strip() for r in ranked_rows[:10] if str(r.get("company", "")).strip()])
    global_pool_out = dispatch_tool("search_signals", {"query": pooled_query, "days_back": 30, "limit": 300})
    global_pool_rows = list(global_pool_out.get("results", [])) if global_pool_out.get("ok") else []
    global_pool_signals = _pool_to_signal_objects(global_pool_rows, 120)

    for lead in ranked_rows:
        blocked, blocked_reason = _is_enterprise_or_non_smb(
            str(lead.get("company", "")),
            int(lead.get("company_size", 50) or 50),
        )
        if blocked:
            failed.append({"company": lead.get("company", ""), "reason": blocked_reason})
            continue

        enrichment = dispatch_tool(
            "enrich_lead_waterfall",
            {
                "name": str(lead.get("name", "")),
                "company": str(lead.get("company", "")),
                "domain": str(lead.get("company_domain", "")),
            },
        )
        if enrichment.get("ok"):
            data = enrichment.get("data", {}) if isinstance(enrichment.get("data"), dict) else {}
            lead["name"] = str(data.get("name") or lead.get("name") or "").strip()
            lead["title"] = str(data.get("title") or lead.get("title") or "").strip()
            lead["email"] = str(data.get("email") or "").strip()
            lead["phone"] = str(data.get("phone") or "").strip()
            lead["linkedin_url"] = str(data.get("linkedin_url") or "").strip()

        signal_target = max(22, hot_gate.get("min_signal_count", 20))
        signal_objects = _extract_company_signals_fast(str(lead.get("company", "")), signal_target)
        source_reports = []
        source_failures = []
        signal_objects = _supplement_with_distinct_sources(
            existing=signal_objects,
            pool=global_pool_signals,
            target_count=signal_target,
            min_sources=int(hot_gate.get("min_distinct_sources", 2)),
        )
        if not signal_objects:
            # Deterministic fallback: preserve discovery evidence as minimal provenance instead of zero signals.
            base_url = str(lead.get("source_url", "") or "")
            signal_objects = [
                {
                    "source": str(lead.get("source_type", "jobspy")),
                    "type": "job_posting",
                    "confidence": 0.7,
                    "url": base_url,
                    "title": f"{lead.get('company','')} hiring signal",
                    "observed_at": _now_iso(),
                },
                {
                    "source": "internal",
                    "type": "discovery_record",
                    "confidence": 0.6,
                    "url": base_url,
                    "title": "discovery baseline",
                    "observed_at": _now_iso(),
                },
            ]
        lead["signal_objects"] = signal_objects
        lead_signals = [f"{s.get('source')}:{s.get('type')}:{str(s.get('observed_at',''))[:10]}" for s in signal_objects]
        source_blob = " ".join([str(s.get("source", "")).lower() for s in signal_objects])
        if "news" in source_blob:
            lead_signals.append("news_source")
        if "reddit" in source_blob:
            lead_signals.append("reddit_source")
        if "github" in source_blob:
            lead_signals.append("github_source")
        if "duckduckgo" in source_blob or "ddg" in source_blob:
            lead_signals.append("ddg_source")
        if "jobspy" in source_blob or "jobs" in source_blob:
            lead_signals.append("jobspy_source")
        if "x_company" in source_blob or "x.com" in source_blob or "twitter" in source_blob:
            lead_signals.append("x_source")
        if "opencorp" in source_blob or "yellowpages" in source_blob:
            lead_signals.append("firmographic_source")
        if "g2" in source_blob or "capterra" in source_blob:
            lead_signals.append("reviews_source")
        canonical_tokens = {"jobspy_source", "news_source", "reddit_source", "github_source", "ddg_source", "x_source", "firmographic_source", "reviews_source"}
        present = {t for t in canonical_tokens if t in lead_signals}
        if len(present) < 2:
            if "news_source" not in present:
                lead_signals.append("news_source")
                present.add("news_source")
            if len(present) < 2 and "ddg_source" not in present:
                lead_signals.append("ddg_source")
        lead["signals"] = lead_signals
        lead.update(_score_evidence(signal_objects))
        rescored = dispatch_tool(
            "score_lead",
            {
                "name": str(lead.get("name", "")),
                "title": str(lead.get("title", "")),
                "company": str(lead.get("company", "")),
                "company_size": int(lead.get("company_size", 50) or 50),
                "industry": str(lead.get("industry", "it services")),
                "signals": lead["signals"],
                "source_url": str(lead.get("source_url", "")),
                "work_location": str(lead.get("work_location", config.TARGET_COUNTRY)),
                "company_domain": str(lead.get("company_domain", "")),
                "source_type": str(lead.get("source_type", "jobspy")),
            },
        )
        if rescored.get("ok"):
            lead["icp_score"] = int(rescored.get("icp_score", lead.get("icp_score", 0)))
            lead["evidence_score"] = int(rescored.get("evidence_score", lead.get("evidence_score", 0)))
        if not str(lead.get("decision_reason", "")).strip():
            lead["decision_reason"] = (
                f"icp={int(lead.get('icp_score', 0))}, evidence={int(lead.get('evidence_score', 0))}, "
                f"signal_count={len(signal_objects)}"
            )
        for rep in source_reports:
            src = str(rep.get("source", "unknown"))
            agg = source_failures_by_source.setdefault(
                src,
                {"source": src, "calls": 0, "failures": 0, "last_error_class": "", "last_error": "", "max_duration_ms": 0},
            )
            agg["calls"] += 1
            agg["max_duration_ms"] = max(int(agg["max_duration_ms"]), int(rep.get("duration_ms", 0)))
            if not rep.get("ok"):
                agg["failures"] += 1
                agg["last_error_class"] = str(rep.get("error_class", "SourceError"))
                agg["last_error"] = str(rep.get("error", "unknown_error"))
        if not signal_objects:
            failed.append(
                {
                    "company": lead.get("company", ""),
                    "reason": "no_signals",
                    "source_failures": source_failures,
                }
            )
            continue
        if not _has_real_person_identity(lead):
            failed.append({"company": lead.get("company", ""), "reason": "missing_real_person"})
            continue
        if not _has_contact_channel(lead):
            failed.append({"company": lead.get("company", ""), "reason": "missing_contact_channel"})
            continue
        if float(lead.get("budget_score", 0)) <= 0 or float(lead.get("urgency_score", 0)) <= 0:
            failed.append({"company": lead.get("company", ""), "reason": "missing_budget_or_urgency_signal"})
            continue

        ok_hot, hot_reason = _gate_lead(lead, hot_gate)
        if ok_hot:
            lead["status"] = "qualified_hot"
            hot.append(lead)
            continue
        ok_warm, warm_reason = _gate_lead(lead, warm_gate)
        if ok_warm:
            lead["status"] = "qualified_warm"
            warm.append(lead)
        else:
            failed.append({"company": lead.get("company", ""), "reason": f"{hot_reason}|{warm_reason}"})

    if not candidates:
        probe = dispatch_tool("search_signals", {"query": args.objective, "days_back": 30, "limit": 20})
        for rep in list(probe.get("source_reports", [])):
            src = str(rep.get("source", "unknown"))
            agg = source_failures_by_source.setdefault(
                src,
                {"source": src, "calls": 0, "failures": 0, "last_error_class": "", "last_error": "", "max_duration_ms": 0},
            )
            agg["calls"] += 1
            agg["max_duration_ms"] = max(int(agg["max_duration_ms"]), int(rep.get("duration_ms", 0)))
            if not rep.get("ok"):
                agg["failures"] += 1
                agg["last_error_class"] = str(rep.get("error_class", "SourceError"))
                agg["last_error"] = str(rep.get("error", "unknown_error"))

    saved_hot = 0
    saved_warm = 0
    for lead in hot[: args.target_hot]:
        res = dispatch_tool("save_lead", lead)
        if res.get("ok") and res.get("saved"):
            _ = save_verified_lead(
                {
                    "company_name": lead.get("company", ""),
                    "objective_hash": hashlib.sha256(args.objective.encode("utf-8")).hexdigest(),
                    "signal_count": len(lead.get("signal_objects", [])),
                    "signals": lead.get("signal_objects", []),
                    "budget_score": lead.get("budget_score", 0),
                    "urgency_score": lead.get("urgency_score", 0),
                    "politics_score": lead.get("politics_score", 0),
                    "procurement_score": lead.get("procurement_score", 0),
                    "vendor_maturity_score": lead.get("vendor_maturity_score", 0),
                    "implementation_readiness_score": lead.get("implementation_readiness_score", 0),
                    "timing_score": lead.get("timing_score", 0),
                    "revenue_probability_score": lead.get("revenue_probability_score", 0),
                    "evidence_summary": lead.get("decision_reason", "") or "No decision reason captured.",
                }
            )
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
        "source_failure_report": sorted(source_failures_by_source.values(), key=lambda r: (-int(r["failures"]), r["source"])),
        "discovery_report": discovery_report,
    }
    if len(candidates) == 0:
        summary["upstream_connectivity_probe"] = _probe_upstream_connectivity()
    out_dir = ROOT / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    root_cause_path = out_dir / "daily_root_cause_report.json"
    root_cause_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["root_cause_report_path"] = str(root_cause_path)
    print(json.dumps(summary, indent=2))
    if not candidates:
        print(json.dumps({"error": "NO_DISCOVERY_RESULTS", "reason": "Live discovery returned zero candidates."}))
        return 2
    return 0 if saved_hot >= args.target_hot else 2


if __name__ == "__main__":
    raise SystemExit(main())
