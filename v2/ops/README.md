# Hermes Ops Dashboard Pack

This pack gives a minimal, standards-first observability path for local and production-like environments.

## What is included

- `prometheus/prometheus.yml`: scrape config for Hermes metrics endpoint.
- `grafana/hermes-overview.json`: starter dashboard with provider/tool latency and error views.
- Runtime metrics endpoint from `v2/scripts/serve_metrics.py`.

## Quick start (local)

1. Run Hermes agent workload in one terminal.
2. Run metrics server in another terminal:
   - `python v2/scripts/serve_metrics.py`
3. Optional: run Prometheus with `v2/ops/prometheus/prometheus.yml`.
4. Import `v2/ops/grafana/hermes-overview.json` into Grafana.

## Notes

- Metrics are event counter and average latency aggregates derived from structured telemetry.
- Sensitive payload content remains redacted by default (`TELEMETRY_REDACT=true`).
- This is intentionally minimal to reduce operational complexity and keep failure modes obvious.

