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
uv sync                          # install: package + dev/deployment groups (uv.lock is truth; Python pinned 3.13 — 3.14 breaks the proxy via uvloop)
uv run pytest tests/ -q          # unit tests — floor: 152 passed
uv run pytest tests/ -m integration -q  # live proxy vs stub upstream — floor: 6 passed, no creds needed (scope to tests/: bare collection hits pgdata/)
uv run ruff check .              # lint — baseline: clean
uv run python serve.py --env .env       # run the proxy on :8001 (needs real .env)
uv run python demo.py --env .env        # live demo battery against the proxy
uv run python tests/smoke_test.py --env <envfile>  # provider connectivity smoke test
scripts/install-hooks.sh         # pre-commit hook (ruff + pytest)
```

Tests are import-shimmed: `uv run pytest tests/test_firewall.py` needs no live
proxy or provider. `demo.py` and `smoke_test.py` need real provider creds.

## Repository constraints

- **Test floor is 152 unit + 6 integration** (legacy baseline was 78; the
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
  `inference_gate/shields.py`); blocks raise `fastapi.HTTPException(400)` so
  LiteLLM logs a guardrail intervention. Shield detail goes to server logs only.

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

## Running deployment

The proxy runs as a foreground process (not a systemd service) inside a tmux
session named `litellm`. A PostgreSQL container backs the management UI.

### Process

- **LiteLLM proxy**: `uv run python serve.py --env .env` on port `0.0.0.0:8001`
- **tmux session**: `litellm` (attach with `tmux a -t litellm`)
- **serve.py**: loads `.env`, refuses to start with an unset or default
  `LITELLM_MASTER_KEY`, then spawns `.venv/bin/litellm --config config.yaml`

### PostgreSQL (management UI backend)

The LiteLLM management UI (`/ui/`) requires a database for user auth and key
management. A Podman container provides PostgreSQL:

| Field | Value |
|-------|-------|
| Container | `litellm-postgres` (Podman, not systemd-managed) |
| Image | `docker.io/library/postgres:16` |
| Port | `127.0.0.1:5433 -> 5432` (localhost only) |
| Data | bind mount `./pgdata/ -> /var/lib/postgresql/data` |
| DB / User | `litellm` / `litellm` |
| Connection string | `DATABASE_URL` in `.env` (points at `localhost:5433`) |

The `pgdata/` directory is owned by the container's postgres UID (not your
host user) with `0700` perms — this is normal. Do not delete it; it holds the
management UI's user/key/spend data.

Start/stop the database:

```bash
podman start litellm-postgres   # start
podman stop litellm-postgres     # stop
```

### Management UI

- **URL**: `http://<host-ip>:8001/ui/`
- **Login**: use `LITELLM_MASTER_KEY` from `.env` as the API key
- The UI requires both PostgreSQL running and `DATABASE_URL` set in `.env`

### Client connections (OpenAI-compatible API)

| Field | Value |
|-------|-------|
| Base URL | `http://<host-ip>:8001/v1` |
| API Key | `LITELLM_MASTER_KEY` from `.env` |
| Model name | `firewall-model` |

All five guardrails run automatically on every request through `firewall-model`.

### Startup sequence (full)

```bash
# 1. Start PostgreSQL
podman start litellm-postgres

# 2. Start LiteLLM proxy (in a tmux session)
tmux new -s litellm
cd ~/github/litellm-firewall
uv run python serve.py --env .env
# Ctrl-B D to detach

# 3. Verify
curl http://localhost:8001/health/liveness   # "I'm alive!"
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:8001/v1/models
```

### Shutdown sequence

```bash
# 1. Stop the proxy (Ctrl-C in the tmux session, or kill the process)
tmux send-keys -t litellm C-c

# 2. Stop PostgreSQL
podman stop litellm-postgres
```

### Guardrail pipeline (config.yaml)

Five shields, all `default_on: true`, attached to `firewall-model`:

| # | Shield | Mode | Type | Catches |
|---|--------|------|------|---------|
| 1 | `inference-gate` | pre_call | Regex/prebuilt | PII, credit cards, secrets, SQL injection, prompt injection |
| 2 | `llama-prompt-guard` | pre_call | LLM classifier (API) | Jailbreak / prompt injection |
| 3 | `prompt-guard-local` | pre_call | Local HF transformers | On-device prompt-attack classifier |
| 4 | `llama-guard` | pre_call | LLM classifier (API) | Harmful content (Llama Guard 3 taxonomy S1-S14) |
| 5 | `response-guard` | post_call | LLM classifier (API) | Output-side exfil/toxic/secret echo |

Advisory shields fail open by default — configurable globally via
`INFERENCE_GATE_FAIL_MODE` or per guardrail via `litellm_params.fail_mode`.
Every shield knob (model, api_base/api_key, threshold, blocked_categories,
timeout, preload) is a `litellm_params` key with env-var fallbacks — the
config surface is documented in the `inference_gate/shields.py` module docstring
and inline in `config.yaml`. Block messages are generic (`BLOCKED_MESSAGE`
in `inference_gate/shields.py`).

### Key files

- `serve.py` — startup script, enforces master key invariant
- `config.yaml` — live proxy config (model list, guardrails, settings)
- `inference_gate/shields.py` — custom guardrail shield implementations
  (pip package `inference-gate`; `firewall_callbacks.py` at the repo root
  is a compat shim for config-file loading — see D-014)
- `.env` — credentials (gitignored, never read into context or commit)
- `pgdata/` — PostgreSQL data (bind mount, container-owned, gitignored)

## File ownership conventions

- `inference_gate/shields.py` — the shield pipeline (LiteLLM adapter layer);
  `firewall_callbacks.py` is a compat shim that must keep re-exporting it
  (config-file guardrail references load by file path — D-014).
- `config.yaml` — live LiteLLM proxy config for the legacy pipeline.
- `docs/security/` — design docs and reports for the transformation.
- `TASKS.yaml` / `WORKLOG.md` / `DECISIONS.md` / `PLAN.md` — canonical work
  state. One agent edits a given file at a time; assign explicit ownership
  when delegating.
