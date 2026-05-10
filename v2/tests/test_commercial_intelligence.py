from __future__ import annotations

import sys
import unittest

sys.path.insert(0, "v2")

from agent.tools import dispatch_tool


class CommercialIntelligenceTests(unittest.TestCase):
    def test_commercial_signal_intelligence_returns_ten_dimensions(self) -> None:
        signals = [
            "series a funding announced",
            "hiring operations manager and revops lead",
            "rfp for crm migration",
            "security review and soc2 requirement",
            "integration roadmap and implementation specialist role",
            "response delay and manual process bottleneck",
        ]
        result = dispatch_tool(
            "commercial_signal_intelligence",
            {
                "company": "Acme Services",
                "industry": "it services",
                "company_size": 55,
                "signals": signals,
                "source_type": "news",
                "source_url": "https://news.ycombinator.com/item?id=1",
            },
        )
        self.assertTrue(result["ok"])
        dims = result["commercial_intelligence"]
        self.assertEqual(len(dims.keys()), 10)
        self.assertGreaterEqual(result["buying_readiness_score"], 1)

    def test_score_lead_embeds_commercial_intelligence(self) -> None:
        result = dispatch_tool(
            "score_lead",
            {
                "name": "Alex Rivera",
                "title": "operations manager",
                "company": "Acme Services",
                "company_size": 45,
                "industry": "it services",
                "signals": [
                    "hiring surge in operations",
                    "crm migration rfp",
                    "integration and implementation project",
                ],
            },
        )
        self.assertTrue(result["ok"])
        self.assertIn("commercial_intelligence", result)
        self.assertIn("buying_readiness_score", result)
        self.assertIn("commercial_confidence_score", result)


if __name__ == "__main__":
    unittest.main()

