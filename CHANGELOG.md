# Changelog

User-visible behavior, configuration, compatibility, and security changes.
(Work journal lives in WORKLOG.md; this file is not a substitute for it.)

## Unreleased

### Added (2026-07-17 — version-policy automation)
- `litellm-bump` workflow: weekly (or manual) litellm upgrade proposals —
  applies the bump, runs the full unit + live-proxy battery against the
  new version, and opens a PR titled with the verdict (D-015).
- Dependabot for routine Python and GitHub Actions updates (litellm
  excluded; it goes through the gated workflow).
- Startup warning when the running litellm differs from
  `TESTED_LITELLM_VERSION`; version sync (constraint / installed /
  constant) is enforced by a unit test.
- `docs/security/LITELLM_VERSION_POLICY.md` — the upgrade policy D-002
  anticipated.

### Added (2026-07-15/16 — shield maturity, UI, packaging)
- **Per-shield configuration** via `litellm_params` with env-var fallbacks:
  `api_base`, `api_key`, `model`, `fail_mode`, `threshold`,
  `blocked_categories`, `timeout`, `preload`. Invalid config fails at proxy
  startup instead of at request time (D-012).
- **Category scoping**: `blocked_categories` (S-codes or taxonomy names)
  limits which Llama Guard 3 categories block; an unsafe verdict without a
  recognizable category always blocks (deny by default).
- **Management-UI integration** (D-013): the four shields register as
  `inference_gate_*` guardrail providers with typed config forms
  (fail-mode select, S1–S14 multiselect); `config.yaml` remains the source
  of truth, UI-created guardrails are DB-managed additions.
- **pip package `inference-gate`** (D-014): bring-your-own-LiteLLM installs
  — the wheel ships only `inference_gate/` with
  `litellm[proxy]>=1.82.0` + `httpx` as dependencies; BYO recipe in README.
- Decision-level logging with latency on every shield evaluation
  (content-free); integration tests for UI provider exposure.

### Changed (2026-07-15/16)
- **Blocks are now guardrail interventions**: shields raise
  `fastapi.HTTPException(400)` (the form LiteLLM records as an intervention
  in guardrail telemetry/metrics) instead of `litellm.BadRequestError`
  (which was logged as a guardrail *failure*). The client-facing message is
  unchanged and still generic.
- **Strict Llama Guard parsing**: guard output must be exactly
  `safe`/`unsafe` (+ S-codes). Malformed output is routed through the fail
  policy (`GuardOutputError`) instead of silently allowing the request.
- A missing guard API base is now a fail-policy event (denies under
  `fail_mode: closed`; previously the shield silently skipped).
- Shields moved to `inference_gate/shields.py`; root `firewall_callbacks.py`
  is a compatibility shim for config-file references.
- Package metadata now declares the tested-open range `litellm>=1.82.0`
  for BYO installs, while this repo's deployment stays exactly pinned via
  `tool.uv.constraint-dependencies` + `uv.lock` (refines the earlier
  exact-pin entry below; D-014). Remote Prompt Guard classification now
  uses async httpx (was blocking urllib in a thread).
- `requirements.txt` is regenerated with `--no-emit-project` (deps only);
  the Docker guide installs the package instead of the requirements export.

### Security
- Shield logging is now content-free: all `print()` calls in
  `firewall_callbacks.py` were replaced with the `inference_gate.shields`
  stdlib logger, which never records prompt/response text, guard-model raw
  output, or exception messages (exception *types* only). Llama Guard block
  logs include only S-codes present in the known taxonomy.
- `demo.py` no longer writes proxy stdout/stderr to `proxy_debug.log` by
  default. Set `INFERENCE_GATE_DEV_DEBUG=1` to opt in; otherwise proxy output
  is discarded (it may contain prompts and responses).
- New log-leak test suite (`tests/test_log_leaks.py`) pins these invariants.

### Changed
- `litellm[proxy]` is now pinned exactly to `1.82.0` (was `>=1.82.0`);
  `openai` constrained to `<3`. `requirements.txt` regenerated from `uv.lock`
  via `uv export` — `uv.lock` is the dependency source of truth
  (DECISIONS.md D-002).

### Fixed
- The local environment had drifted to Python 3.14, where uvloop cannot
  import and **the proxy could not start at all**. The project is now pinned
  to Python 3.13 via `.python-version` (CI still tests 3.12 and 3.13 via
  `uv sync --python`).

### Added
- Live-proxy integration test suite (`tests/test_integration_proxy.py`,
  `pytest -m integration`): boots the real LiteLLM proxy against a stub
  OpenAI-compatible upstream — no credentials needed — and asserts safe
  pass-through, deterministic and Llama Guard blocks (generic error, provider
  never called), and response-side output blocking. Runs in CI.
- `docs/security/OPERATIONS.md` — TLS deployment requirements and the
  verified litellm 1.82.0 CORS limitation (hardcoded `origins=["*"]`; must be
  enforced at ingress).
- v2 transformation work-state system: `AGENTS.md`, `TASKS.yaml`,
  `WORKLOG.md`, `DECISIONS.md`, `docs/security/` (OBJECTIVE, GUARD_MODELS,
  LITELLM_INTEGRATION, legacy-baseline report).
