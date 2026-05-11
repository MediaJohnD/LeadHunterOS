from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.hermes_agent import HermesAgent


class _StubRouter:
    available_backends = ["stub"]

    def route(self, messages):  # pragma: no cover - deterministic mode bypasses this
        return {"content": "FINAL ANSWER: stub", "backend": "stub", "model": "stub", "latency_ms": 1}


class Phase2HardeningTests(unittest.TestCase):
    def test_parse_recovery_from_params_key(self) -> None:
        agent = HermesAgent(router=_StubRouter(), tool_dispatcher=lambda n, a: {"ok": True})
        content = '<tool_call>{"name":"search_news_signals","params":{"query":"US SMB"}}</tool_call>'
        calls, errors = agent._parse_tool_calls(content)
        self.assertEqual(len(errors), 0)
        self.assertEqual(calls[0]["name"], "search_news_signals")
        self.assertIn("arguments", calls[0])

    def test_deterministic_mode_returns_payload(self) -> None:
        def dispatcher(name, arguments):
            if name == "search_jobs_by_icp":
                return {
                    "ok": True,
                    "results": [
                        {
                            "company": "Acme Co",
                            "title": "operations manager",
                            "company_domain": "acme.co",
                            "url": "https://example.com/job",
                        }
                    ],
                }
            if name == "search_news_signals":
                return {"ok": True, "results": []}
            if name == "rank_leads":
                leads = arguments.get("leads", [])
                for lead in leads:
                    lead["icp_score"] = 90
                    lead["evidence_score"] = 70
                    lead["decision_reason"] = "Qualified"
                return {"ok": True, "results": leads}
            if name == "orchestrate_playbook":
                return {"ok": True, "selected_for_crm_handoff": arguments.get("leads", [])}
            if name == "save_lead":
                lead = dict(arguments)
                lead["signals"] = lead.get("signals", []) + ["news_source", "reddit_source"]
                lead["source_url"] = lead.get("source_url") or "https://example.com"
                return {"ok": True, "saved": True, "lead": lead}
            return {"ok": True}

        agent = HermesAgent(router=_StubRouter(), tool_dispatcher=dispatcher)
        result = agent.run("Find leads")
        self.assertEqual(result.get("mode"), "deterministic")
        self.assertIn("leads_saved", result)


if __name__ == "__main__":
    unittest.main()
