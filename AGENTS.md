# AGENTS.md — Operating Manual for AI Agents

Permanent operating instructions for any agent (OpenCode, Claude Code, or other)
working on InferenceGate. Read this first, every session.

## What this project is

InferenceGate is an LLM security gateway built on LiteLLM Proxy. It is being
transformed from a fixed five-shield guardrail demo into an enterprise,
policy-driven security-control platform (detection separated from enforcement,
Telltale-compatible rules, secret dehydration/rehydration, multi-tenancy).
The full target specification lives in `docs/security/OBJECTIVE.md`.

## Session startup (mandatory order)

1. Read this file.
2. Read `PLAN.md` (roadmap + current phase).
3. Read `TASKS.yaml` (machine-readable task state; `next_task` is authoritative).
4. Read the newest entries in `WORKLOG.md`.
5. Read unresolved entries in `DECISIONS.md`.
6. Run `git status`; record branch + HEAD; compare against recorded task state.
7. Resume the recorded next action. Do not restart planning from scratch.

## Session shutdown (mandatory)

Update `TASKS.yaml`, append to `WORKLOG.md` (never rewrite old entries),
update `PLAN.md`/`GAP_ANALYSIS.md` if reality changed, record the exact next
action, and confirm no plaintext secret entered any log, fixture, or report.

## Commands

```bash
uv sync --extra dev              # install (uv.lock is the source of truth; Python pinned 3.13 — 3.14 breaks the proxy via uvloop)
uv run pytest tests/ -q          # unit tests — floor: 100 passed
uv run pytest -m integration -q  # live proxy vs stub upstream — floor: 4 passed, no creds needed
uv run ruff check .              # lint — baseline: clean
uv run python serve.py --env .env       # run the proxy on :8001 (needs real .env)
uv run python demo.py --env .env        # live demo battery against the proxy
uv run python tests/smoke_test.py --env <envfile>  # provider connectivity smoke test
scripts/install-hooks.sh         # pre-commit hook (ruff + pytest)
```

Tests are import-shimmed: `uv run pytest tests/test_firewall.py` needs no live
proxy or provider. `demo.py` and `smoke_test.py` need real provider creds.

## Repository constraints

- **Test floor is 100 unit + 4 integration** (legacy baseline was 78; the
  "39" in older docs is stale). Never finish with fewer passing tests than
  the floor.
- `inference_gate/contracts.py` is the normative control-plane vocabulary
  (P1). Changing Action precedence, Mode semantics, or TenantContext
  fail-closed behavior requires a DECISIONS.md entry.
- LiteLLM is pinned at **1.82.0** via `uv.lock`. `requirements.txt` is a stale
  legacy export (Mar 2026) — do not install from it; see DECISIONS.md D-002.
- Python >=3.10; CI runs 3.12 and 3.13 with `uv`. Gitleaks already runs in CI.
- `.env`, `.go.env`, `.groq.env` hold real credentials and are gitignored.
  **Never read them into context, print them, or commit them.** `typescript`
  and `proxy_debug.log` are gitignored local artifacts — leave them alone.
- The LiteLLM master key must never default: `serve.py` refuses to start with
  an unset or default key. Preserve this invariant.
- Client-facing block errors must stay generic (`BLOCKED_MESSAGE` in
  `firewall_callbacks.py:39`). Shield detail goes to server logs only.

## Security invariants (never silently bypassable)

- No plaintext secrets in logs, traces, metrics, findings, fixtures, errors,
  cache keys, or reports.
- Tenant isolation, manifest integrity, rehydration authorization, and config
  validation may be disabled as whole features but never weakened while enabled.
- Detection is separate from enforcement: detectors produce findings; policy
  decides actions. Do not couple a detector to blocking.
- Fail behavior: advisory reviewers may fail open with an alert; transformers,
  manifests, rehydration, and final DLP fail closed.

## Rules for changes

- Preserve pre-existing user work. No destructive git commands (reset --hard,
  clean, force-checkout). Local commits only; never push/merge/PR unless asked.
- Run `uv run pytest tests/ -q` and `uv run ruff check .` before finishing any
  code change. Review your own `git diff`.
- Do not do a large file reorganization before compatibility tests exist
  (see PLAN.md phase gates).
- Licensing: secret-detection rules may come only from Telltale (Apache-2.0),
  Gitleaks (MIT), Titus (Apache-2.0), Yelp detect-secrets (Apache-2.0),
  Secretlint (MIT), Nosey Parker (Apache-2.0, legacy only). **Never** from
  TruffleHog (AGPL), DataSentry (GPL), Semgrep community rules, or
  unknown-license sources. Record provenance in `config/security/sources.lock.yaml`.

## File ownership conventions

- `firewall_callbacks.py` — legacy shield pipeline; being migrated to a thin
  LiteLLM adapter. Keep it working until `legacy-default` parity tests pass.
- `config.yaml` — live LiteLLM proxy config for the legacy pipeline.
- `docs/security/` — design docs and reports for the transformation.
- `TASKS.yaml` / `WORKLOG.md` / `DECISIONS.md` / `PLAN.md` — canonical work
  state. One agent edits a given file at a time; assign explicit ownership
  when delegating.
