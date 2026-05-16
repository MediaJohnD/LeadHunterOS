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
        rows.append(
            {
                "source": source,
                "type": "news_article" if source == "news" else "job_posting",
                "confidence": 0.9,
                "url": f"https://example.com/{source}/{i}",
                "title": f"{source} evidence {i}",
                "observed_at": "2026-05-10T00:00:00+00:00",
            }
        )
    return rows


class ProductionGatesTests(unittest.TestCase):
    def test_daily_batch_meets_strict_hot_contract(self) -> None:
        module = _load_daily_batch_module()
        candidates = [
            {
                "name": f"Lead {i}",
                "title": "operations manager",
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
                module, "_extract_company_signals_fast", side_effect=lambda *_args, **_kwargs: _mk_signals(26)
            ), patch.object(module, "_pool_to_signal_objects", return_value=[]), patch.object(
                module, "_probe_upstream_connectivity", return_value=[]
            ), patch.object(module, "save_verified_lead", return_value={"ok": True}), patch.object(
                module, "export_latest_leads_csv", return_value={"path": "leads_latest.csv", "rows": 10}
            ), patch.object(module, "dispatch_tool") as mock_dispatch:
                def _dispatch(name: str, args: dict):
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
                "name": f"Lead {i}",
                "title": "operations manager",
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
                module, "_extract_company_signals_fast", side_effect=lambda *_args, **_kwargs: _mk_signals(24)
            ), patch.object(module, "_pool_to_signal_objects", return_value=[]), patch.object(
                module, "_probe_upstream_connectivity", return_value=[]
            ), patch.object(module, "save_verified_lead", return_value={"ok": True}), patch.object(
                module, "export_latest_leads_csv", return_value={"path": "leads_latest.csv", "rows": 3}
            ), patch.object(module, "dispatch_tool") as mock_dispatch:
                save_counter = {"count": 0}

                def _dispatch(name: str, args: dict):
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

    def test_ssl_fallback_probe_is_instrumented(self) -> None:
        module = _load_daily_batch_module()

        class _OkResponse:
            status_code = 200

        def _fake_get(_url: str, **kwargs):
            if kwargs.get("verify", True):
                raise requests.exceptions.SSLError("certificate verify failed")
            return _OkResponse()

        with patch.object(module.requests, "get", side_effect=_fake_get):
            rows = module._probe_upstream_connectivity()
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(all(row["verify_false_ok"] for row in rows))
        self.assertTrue(any(row["error_class"] == "SSLError" for row in rows))


if __name__ == "__main__":
    unittest.main()
