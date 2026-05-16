from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_daily_hot_batch.py"


def _load_daily_batch_module():
    spec = importlib.util.spec_from_file_location("run_daily_hot_batch", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load run_daily_hot_batch module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mk_signals(count: int = 24) -> list[dict]:
    rows: list[dict] = []
    sources = ["news", "reddit", "github", "ddg", "jobspy"]
    for i in range(count):
        source = sources[i % len(sources)]
        if source == "news":
            signal_type = "news_article"
        elif source == "reddit":
            signal_type = "reddit_post"
        elif source == "github":
            signal_type = "github_repo"
        else:
            signal_type = "job_posting"
        rows.append(
            {
                "source": source,
                "type": signal_type,
                "confidence": 0.9,
                "url": f"https://example.com/{source}/{i}",
                "title": f"{source} evidence {i}",
                "observed_at": "2026-05-10T00:00:00+00:00",
            }
        )
    return rows


class ProductionGatesTests(unittest.TestCase):
    def _run_daily_main_for_single_candidate(
        self,
        module,
        *,
        candidate: dict,
        enrich_data: dict | None,
        signal_count: int = 26,
        score_icp: int = 92,
        score_evidence: int = 88,
    ) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            gate_file = Path(tmp) / "hot_warm_gating.yaml"
            gate_file.write_text("", encoding="utf-8")
            with patch.object(module, "_build_candidates", return_value=([candidate], [])), patch.object(
                module, "_extract_signals", side_effect=lambda *_args, **_kwargs: (_mk_signals(signal_count), [], [])
            ), patch.object(module, "_pool_to_signal_objects", return_value=[]), patch.object(
                module, "_probe_upstream_connectivity", return_value=[]
            ), patch.object(module, "save_verified_lead", return_value={"ok": True}), patch.object(
                module, "export_latest_leads_csv", return_value={"path": "leads_latest.csv", "rows": 0}
            ), patch.object(module, "dispatch_tool") as mock_dispatch:
                def _dispatch(name: str, args: dict):
                    if name == "enrich_lead_waterfall":
                        return {"ok": True, "data": dict(enrich_data or {})}
                    if name == "rank_leads":
                        return {"ok": True, "results": args.get("leads", [])}
                    if name == "score_lead":
                        return {"ok": True, "icp_score": score_icp, "evidence_score": score_evidence}
                    if name == "save_lead":
                        return {"ok": True, "saved": True, "lead": dict(args)}
                    if name == "search_signals":
                        return {"ok": True, "results": [], "source_reports": [], "source_failures": []}
                    return {"ok": True, "results": []}

                mock_dispatch.side_effect = _dispatch
                with patch(
                    "sys.argv",
                    [
                        "run_daily_hot_batch.py",
                        "--gating",
                        str(gate_file),
                        "--target-hot",
                        "1",
                        "--target-warm",
                        "0",
                        "--objective",
                        "strict gate test",
                    ],
                ):
                    rc = module.main()
        return rc

    def test_daily_batch_meets_strict_hot_contract(self) -> None:
        module = _load_daily_batch_module()
        candidates = [
            {
                "name": f"Jordan Smith {i}",
                "title": "VP Operations",
                "company": f"Company {i}",
                "company_domain": f"company{i}.com",
                "industry": "it services",
                "company_size": 50,
                "work_location": "United States",
                "source_type": "jobspy",
                "source_url": "https://example.com/job",
                "signals": ["jobspy_source", "news_source", "reddit_source"],
                "decision_reason": "deterministic candidate",
            }
            for i in range(12)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            gate_file = Path(tmp) / "hot_warm_gating.yaml"
            gate_file.write_text("", encoding="utf-8")
            with patch.object(module, "_build_candidates", return_value=(candidates, [])), patch.object(
                module, "_extract_signals", side_effect=lambda *_args, **_kwargs: (_mk_signals(26), [], [])
            ), patch.object(module, "_pool_to_signal_objects", return_value=[]), patch.object(
                module, "_probe_upstream_connectivity", return_value=[]
            ), patch.object(module, "save_verified_lead", return_value={"ok": True}), patch.object(
                module, "export_latest_leads_csv", return_value={"path": "leads_latest.csv", "rows": 10}
            ), patch.object(module, "dispatch_tool") as mock_dispatch:
                def _dispatch(name: str, args: dict):
                    if name == "enrich_lead_waterfall":
                        return {
                            "ok": True,
                            "data": {
                                "name": str(args.get("name", "Jordan Smith")),
                                "title": "VP Operations",
                                "email": f"vp{args.get('company', 'company').lower().replace(' ', '')}@companymail.com",
                                "linkedin_url": f"https://linkedin.com/in/{str(args.get('company', 'company')).lower().replace(' ', '-')}",
                            },
                        }
                    if name == "rank_leads":
                        return {"ok": True, "results": args.get("leads", [])}
                    if name == "score_lead":
                        return {"ok": True, "icp_score": 92, "evidence_score": 88}
                    if name == "save_lead":
                        return {"ok": True, "saved": True, "lead": dict(args)}
                    if name == "search_signals":
                        return {"ok": True, "results": [], "source_reports": [], "source_failures": []}
                    return {"ok": True, "results": []}

                mock_dispatch.side_effect = _dispatch
                with patch(
                    "sys.argv",
                    [
                        "run_daily_hot_batch.py",
                        "--gating",
                        str(gate_file),
                        "--target-hot",
                        "10",
                        "--target-warm",
                        "0",
                        "--objective",
                        "fintech atlanta series b",
                    ],
                ):
                    rc = module.main()
            self.assertEqual(rc, 0)

    def test_daily_batch_fails_with_actionable_contract_reason(self) -> None:
        module = _load_daily_batch_module()
        candidates = [
            {
                "name": f"Jordan Smith {i}",
                "title": "VP Operations",
                "company": f"Company {i}",
                "company_domain": f"company{i}.com",
                "industry": "it services",
                "company_size": 50,
                "work_location": "United States",
                "source_type": "jobspy",
                "source_url": "https://example.com/job",
                "signals": ["jobspy_source", "news_source", "reddit_source"],
                "decision_reason": "deterministic candidate",
            }
            for i in range(10)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            gate_file = Path(tmp) / "hot_warm_gating.yaml"
            gate_file.write_text("", encoding="utf-8")
            with patch.object(module, "_build_candidates", return_value=(candidates, [])), patch.object(
                module, "_extract_signals", side_effect=lambda *_args, **_kwargs: (_mk_signals(24), [], [])
            ), patch.object(module, "_pool_to_signal_objects", return_value=[]), patch.object(
                module, "_probe_upstream_connectivity", return_value=[]
            ), patch.object(module, "save_verified_lead", return_value={"ok": True}), patch.object(
                module, "export_latest_leads_csv", return_value={"path": "leads_latest.csv", "rows": 3}
            ), patch.object(module, "dispatch_tool") as mock_dispatch:
                save_counter = {"count": 0}

                def _dispatch(name: str, args: dict):
                    if name == "enrich_lead_waterfall":
                        return {
                            "ok": True,
                            "data": {
                                "name": str(args.get("name", "Jordan Smith")),
                                "title": "VP Operations",
                                "email": f"vp{args.get('company', 'company').lower().replace(' ', '')}@companymail.com",
                                "linkedin_url": f"https://linkedin.com/in/{str(args.get('company', 'company')).lower().replace(' ', '-')}",
                            },
                        }
                    if name == "rank_leads":
                        return {"ok": True, "results": args.get("leads", [])}
                    if name == "score_lead":
                        return {"ok": True, "icp_score": 92, "evidence_score": 88}
                    if name == "save_lead":
                        save_counter["count"] += 1
                        if save_counter["count"] <= 3:
                            return {"ok": True, "saved": True, "lead": dict(args)}
                        return {"ok": False, "saved": False, "error": "simulated_save_failure"}
                    if name == "search_signals":
                        return {"ok": True, "results": [], "source_reports": [], "source_failures": []}
                    return {"ok": True, "results": []}

                mock_dispatch.side_effect = _dispatch
                with patch(
                    "sys.argv",
                    [
                        "run_daily_hot_batch.py",
                        "--gating",
                        str(gate_file),
                        "--target-hot",
                        "10",
                        "--target-warm",
                        "0",
                        "--objective",
                        "fintech atlanta series b",
                    ],
                ):
                    rc = module.main()
            self.assertEqual(rc, 2)
            report = ROOT / "evals" / "daily_root_cause_report.json"
            self.assertTrue(report.exists())
            payload = report.read_text(encoding="utf-8")
            parsed = __import__("json").loads(payload)
            self.assertEqual(int(parsed.get("saved_hot", -1)), 3)
            self.assertEqual(int(parsed.get("target_hot", -1)), 10)

    def test_tls_verified_only_probe_records_ssl_errors(self) -> None:
        module = _load_daily_batch_module()

        def _fake_get(_url: str, **kwargs):
            self.assertTrue(kwargs.get("verify", True))
            raise requests.exceptions.SSLError("certificate verify failed")

        with patch.object(module.requests, "get", side_effect=_fake_get):
            rows = module._probe_upstream_connectivity()
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(all(not row["verify_true_ok"] for row in rows))
        self.assertTrue(any(row["error_class"] == "SSLError" for row in rows))

    def test_missing_real_person_fail_path(self) -> None:
        module = _load_daily_batch_module()
        candidate = {
            "name": "Ops Contact",
            "title": "operations manager",
            "company": "Acme Field Services",
            "company_domain": "acmefieldservices.com",
            "industry": "home services",
            "company_size": 60,
            "work_location": "United States",
            "source_type": "jobspy",
            "source_url": "https://example.com/job",
            "signals": ["jobspy_source", "news_source", "reddit_source"],
            "decision_reason": "deterministic candidate",
        }
        rc = self._run_daily_main_for_single_candidate(
            module,
            candidate=candidate,
            enrich_data={
                "name": "Ops Contact",
                "title": "operations manager",
                "email": "ops@acmefieldservices.com",
                "linkedin_url": "",
            },
        )
        self.assertEqual(rc, 2)
        report = ROOT / "evals" / "daily_root_cause_report.json"
        parsed = __import__("json").loads(report.read_text(encoding="utf-8"))
        reasons = [str(row.get("reason", "")) for row in parsed.get("failed_sample", [])]
        self.assertIn("missing_real_person", reasons)

    def test_missing_verified_email_fail_path(self) -> None:
        module = _load_daily_batch_module()
        candidate = {
            "name": "Jordan Smith",
            "title": "VP Operations",
            "company": "Acme Field Services",
            "company_domain": "acmefieldservices.com",
            "industry": "home services",
            "company_size": 60,
            "work_location": "United States",
            "source_type": "jobspy",
            "source_url": "https://example.com/job",
            "signals": ["jobspy_source", "news_source", "reddit_source"],
            "decision_reason": "deterministic candidate",
        }
        rc = self._run_daily_main_for_single_candidate(
            module,
            candidate=candidate,
            enrich_data={
                "name": "Jordan Smith",
                "title": "VP Operations",
                "email": "jordan.smith@example.com",
                "linkedin_url": "https://linkedin.com/in/jordan-smith",
            },
        )
        self.assertEqual(rc, 2)
        report = ROOT / "evals" / "daily_root_cause_report.json"
        parsed = __import__("json").loads(report.read_text(encoding="utf-8"))
        reasons = [str(row.get("reason", "")) for row in parsed.get("failed_sample", [])]
        self.assertIn("missing_verified_email", reasons)

    def test_enterprise_blocklist_fail_path(self) -> None:
        module = _load_daily_batch_module()
        candidate = {
            "name": "Jordan Smith",
            "title": "VP Operations",
            "company": "Google",
            "company_domain": "google.com",
            "industry": "software",
            "company_size": 300,
            "work_location": "United States",
            "source_type": "jobspy",
            "source_url": "https://example.com/job",
            "signals": ["jobspy_source", "news_source", "reddit_source"],
            "decision_reason": "deterministic candidate",
        }
        rc = self._run_daily_main_for_single_candidate(
            module,
            candidate=candidate,
            enrich_data={
                "name": "Jordan Smith",
                "title": "VP Operations",
                "email": "jordan.smith@google.com",
                "linkedin_url": "https://linkedin.com/in/jordan-smith",
            },
        )
        self.assertEqual(rc, 2)
        report = ROOT / "evals" / "daily_root_cause_report.json"
        parsed = __import__("json").loads(report.read_text(encoding="utf-8"))
        reasons = [str(row.get("reason", "")) for row in parsed.get("failed_sample", [])]
        self.assertIn("enterprise_blocklist", reasons)


if __name__ == "__main__":
    unittest.main()
