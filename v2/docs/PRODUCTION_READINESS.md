# Hermes Agent Production Readiness

This document defines how to evaluate, replay, tune, and observe Hermes Agent.

## 1) Eval and Regression Gates

### Run unit + scenario evals

```powershell
python -m unittest discover -s v2/tests -p "test_*.py" -q
python v2/evals/harness.py
```

### What the eval harness checks

- Tool-call happy path (`search_signals -> rank_leads -> orchestrate_playbook -> FINAL ANSWER`)
- Malformed tool-call recovery
- Safety boundary handling (placeholder lead blocking)
- Machine-checkable pass/fail assertions per fixture

Fixtures live in `v2/evals/fixtures/*.json`.

## 2) Provider Adapter Model

Adapters live in `v2/agent/providers`.

Each adapter implements:

- `is_configured()`
- `detect_available()`
- `capabilities()`
- `default_model()`
- `complete(request)`

Errors are normalized through `LLMProviderError` with:

- `kind`: auth/rate_limit/timeout/network/bad_request/server/unavailable/parse/unknown
- `retryable`: true/false
- `status_code`

## 3) Trajectory Replay and Tuning

### Trajectory capture

Trajectories are written to `v2/trajectories/*.json` when `TRAJECTORY_ENABLED=true` (default).

### Replay and diff

```powershell
python v2/scripts/replay_trajectory.py --path v2/trajectories/<file>.json
python v2/scripts/replay_trajectory.py --path old.json --compare new.json
```

### Tuning experiments (explicit and reversible)

```powershell
python v2/scripts/tuning_experiments.py
```

Outputs `v2/evals/experiment_results.json`.

## 4) Observability

Telemetry events are written to `telemetry.jsonl`.

Environment controls:

- `TELEMETRY_ENABLED=true|false`
- `TELEMETRY_REDACT=true|false`
- `TELEMETRY_SAMPLE_RATE=0.0-1.0`

Prometheus-ready metrics are exposed from telemetry via `export_prometheus()`.

## 5) CI Regression Gate

GitHub Actions workflow:

- `.github/workflows/hermes-regression.yml`

Gate sequence:

1. Install dependencies
2. Compile check
3. Unit tests
4. End-to-end eval harness

Any failure blocks the pipeline.

## 6) Live Provider Smoke Lane

Workflow:

- `.github/workflows/live-provider-smoke.yml`

This lane is manual by design (`workflow_dispatch`) so operators can run real-provider checks on demand without adding unstable external dependency risk to every PR.

### Required GitHub repository secrets

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `PERPLEXITY_API_KEY`

### Run locally

```powershell
python v2/scripts/live_provider_smoke.py
```

Optional provider subset:

```powershell
$env:SMOKE_PROVIDERS="openai,claude"
python v2/scripts/live_provider_smoke.py
```

### Pass/fail behavior

- `SKIP`: provider not configured locally.
- `PASS`: provider answered minimal deterministic prompt.
- `FAIL`: provider configured but unavailable, malformed response, or normalized adapter error.

## 7) Operator Quickstart (PowerShell)

```powershell
cd "C:\Windows\System32\LeadHunterOS"
git pull --ff-only origin main
cd "C:\Windows\System32\LeadHunterOS\v2"
python -m py_compile config.py run_agent.py agent\hermes_agent.py agent\llm_router.py agent\tools.py
python -m unittest discover -s tests -p "test_*.py" -q
python evals\harness.py
python scripts\live_provider_smoke.py
python run_agent.py --status
python run_agent.py --timeline --objective "Find high-fit US SMB leads with strong ICP + intent signals; score and rank top 3."
```
