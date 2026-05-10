# LeadHunterOS v2 Workspace Map

This file defines the authoritative structure for `LeadHunterOS/v2`.

## Canonical Scope

- Product code, tests, docs, evals, and scripts for the active v2 system live under `v2/`.
- GitHub `main` is the canonical source of truth.

## Authoritative v2 Layout

- `v2/agent/` — agent runtime, tools, providers, routing, telemetry, trajectory.
- `v2/evals/` — eval harness, fixtures, and experiment artifacts intended for source control.
- `v2/tests/` — unit/integration regression coverage and stable fixtures.
- `v2/scripts/` — operator and developer scripts (eval/run/replay/smoke/calibration).
- `v2/docs/` — durable technical and operational documentation.
- `v2/ops/` — observability packs (Grafana/Prometheus config and ops docs).
- `v2/ui/` — Next.js UX surface and brand system.
- `v2/brand/` — shared brand tokens/assets only when not scoped to `v2/ui/brand`.

## Placement Rules

1. New v2 code must be added under existing folders above; avoid creating new top-level folders unless required.
2. UI assets/components should stay under `v2/ui/` (prefer `v2/ui/brand` for UX brand system).
3. Generated runtime outputs should not be committed unless explicitly designated as fixtures.

## Disallowed/Guarded Patterns

- Nested `v2` paths (example: `v2/**/v2/**`) are not allowed.
- Duplicate workspaces inside the repo are not allowed.
- Build/cache artifacts are local-only (`node_modules/`, `.next/`, `__pycache__/`, etc.).

## Local-Only Artifacts (Not Canonical)

- Local env files (`.env`, `.env.*` containing secrets).
- Runtime/export outputs recreated per run (unless promoted to fixtures).
- Temporary logs, caches, screenshots, and scratch notes.

## Review Checklist for Structural Changes

Before merging structural changes:

1. Confirm all moved files remain under `v2/`.
2. Confirm no nested `v2` directories are introduced.
3. Confirm imports/docs were updated after moves.
4. Confirm tests/evals still run from canonical paths.
