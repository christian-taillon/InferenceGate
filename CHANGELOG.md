# Changelog

User-visible behavior, configuration, compatibility, and security changes.
(Work journal lives in WORKLOG.md; this file is not a substitute for it.)

## Unreleased

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
