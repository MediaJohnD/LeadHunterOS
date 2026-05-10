from __future__ import annotations

import sys
import unittest

sys.path.insert(0, "v2")

from agent.tools import dispatch_tool


class QualityGatesTests(unittest.TestCase):
    def test_save_lead_rejects_placeholder(self) -> None:
        result = dispatch_tool(
            "save_lead",
            {
                "name": "John Doe",
                "title": "operations manager",
                "company": "Example Company",
                "company_domain": "example.com",
                "industry": "it services",
                "company_size": 50,
                "signals": ["hiring"],
                "source_url": "https://example.com/news",
                "source_type": "news",
            },
        )
        self.assertFalse(result["ok"])

    def test_orchestrate_emits_trigger_playbooks(self) -> None:
        result = dispatch_tool(
            "orchestrate_playbook",
            {
                "objective": "test",
                "leads": [
                    {
                        "name": "Jane Roe",
                        "title": "operations manager",
                        "company": "Acme Services",
                        "company_domain": "acme-services.com",
                        "industry": "it services",
                        "company_size": 40,
                        "signals": ["series a funding announced", "hiring surge in customer success"],
                        "source_type": "news",
                        "source_url": "https://news.example.com/acme",
                    }
                ],
            },
        )
        self.assertTrue(result["ok"])
        self.assertIn("trigger_playbooks", result)

    def test_enrich_waterfall_emits_contact_tier(self) -> None:
        result = dispatch_tool(
            "enrich_lead_waterfall",
            {"name": "Jane Roe", "company": "Acme Services", "domain": "acme-services.com"},
        )
        self.assertTrue(result["ok"])
        self.assertIn("contact_resolution_tier", result["data"])


if __name__ == "__main__":
    unittest.main()
