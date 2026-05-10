# Beat-the-Field Execution Matrix

Last updated: 2026-05-10

This matrix defines the minimum competitive bar against 11x, Artisan, AiSDR, Salesforge, and Gojiberry-style workflows.

## Capability Matrix (Testable)

| Capability | Acceptance Criteria | Test/Gate |
|---|---|---|
| Ranked free-signal waterfall | `search_signals` returns `waterfall_applied=true`, `no_paid_sources_used=true`, and rank metadata | `dispatch_tool("search_signals", ...)` contract check |
| 10 hidden commercial dimensions | Tool returns budget/urgency/politics/procurement/vendor/board/maturity/alignment/committee/readiness with evidence | `test_commercial_intelligence.py` |
| Explainable scoring | `score_lead` includes `commercial_intelligence` + readiness/confidence fields | `test_commercial_intelligence.py` |
| Anti-noise hard gates | Placeholder and low-evidence leads blocked from persistence | `test_quality_gates.py` |
| Deterministic orchestration | Required tool-flow and anti-repeat loop guards active | `test_eval_harness.py`, `test_llm_router.py` |
| 10x/day reliability | 10 sequential eval cycles pass >=90% | `v2/scripts/run_beat_field_gate.py` |
| Release safety | Release is blocked when scoreboard is not green | `v2/evals/beat_field_scoreboard.json` + gate script exit code |

## Missing Capability Patch Queue (Priority)

1. BuiltWith/Wappalyzer free adapters (tech-stack confidence)
2. G2/Capterra public review parsers (pain language depth)
3. OpenCorporates/YellowPages firmographic validators
4. X/Twitter company signal parser (public post momentum)
5. Postgres + vector-memory dual-store production profile (SQLite fallback remains for local continuity)

## UX Standard (Evidence-first)

The UX should follow evidence-based distinctiveness and memory principles:

- Every score must show **why** (evidence snippets + sources).
- Every recommendation must show **confidence** and **unknowns**.
- Every user flow should minimize ambiguity with deterministic gate reasons.
- No synthetic lead examples in production surfaces.

This prioritizes trust, decision confidence, and repeatability over decorative UI patterns.

