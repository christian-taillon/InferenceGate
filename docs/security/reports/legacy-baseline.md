# Legacy Baseline Report

Verified empirically on **2026-07-12** during workspace preparation, before any
transformation code was written. This is the parity target for the
`legacy-default` compatibility profile (Phase 4).

## Repository state

| Item | Value |
|---|---|
| Branch | `main` (2 commits ahead of `origin/main`, unpushed) |
| HEAD | `784bb21` — "docs: update README with current architecture and phase 4 response scanning" |
| Working tree | clean (only untracked `.claude/` session dir) |
| Pre-existing local files | `.env`, `.go.env`, `.groq.env` (gitignored, real creds — do not read), `typescript` (script(1) recording), `proxy_debug.log` (empty) |

## Verified baseline

| Check | Result | Command |
|---|---|---|
| Unit tests | **78 passed** in ~1.2s (55 test functions, parametrization expands to 78) | `uv run pytest tests/test_firewall.py -q` |
| Ruff | clean, no findings | `uv run ruff check .` |
| LiteLLM version | **1.82.0** pinned in `uv.lock`; `pyproject.toml` declares `litellm[proxy]>=1.82.0` (range, not exact) | — |
| Python | requires `>=3.10`; CI matrix 3.12 + 3.13 via `uv` | `.github/workflows/test.yml` |
| CI secret scanning | **already present** — gitleaks-action@v2 runs before tests | `.github/workflows/test.yml:24-27` |

> ⚠️ **Correction to prior documents:** PLAN.md Phase 4/5 and the transformation
> brief cite "39 tests". The suite has since grown; the actual verified baseline
> is **78 passing tests**. 39 is stale — never regress below 78.

## Shield pipeline (execution order per `config.yaml` guardrails list)

All attached to the single `firewall-model` alias; all `default_on: true`.

| # | Guardrail name | Class / mechanism | Mode | Behavior |
|---|---|---|---|---|
| 1 | `inference-gate` | LiteLLM `litellm_content_filter` (prebuilt: iban, credit_card, us_ssn, email, ipv4, aws_access_key, generic_api_key; regex: JWT, SQL injection, prompt injection) | `pre_call` | BLOCK on match |
| 2 | `llama-prompt-guard` | `LlamaPromptGuardShield` — remote Prompt Guard 2 via `/classify` endpoint, chat-completion fallback for Groq; 350-word chunking with 50-word overlap | `pre_call` | block ≥0.5 malicious |
| 3 | `prompt-guard-local` | `PromptGuardLocalShield` — local HF transformers pipeline, `PROMPT_GUARD_LOCAL_MODEL` (default `meta-llama/Llama-Prompt-Guard-2-86M`), threshold env `PROMPT_GUARD_LOCAL_THRESHOLD` (0.5); fails open if transformers/torch missing | `pre_call` | block ≥ threshold |
| 4 | `llama-guard` | `LlamaGuardShield` — Llama Guard 3 via chat completion, S1–S14 taxonomy parsing | `pre_call` | block on "unsafe" |
| 5 | `response-guard` | `ResponseGuardShield` — re-uses Llama Guard against model output via `async_post_call_success_hook` | `post_call` | block on "unsafe" |

### Hook wiring caveat (verify in Phase 0.5)

`config.yaml` declares `mode: "pre_call"` but the custom shields implement
`async_moderation_hook` and `apply_guardrail` (not `async_pre_call_hook`).
Which hook LiteLLM 1.82.0 actually dispatches for these modes must be confirmed
empirically before the adapter is built (task `p05.capability-matrix`).
`ResponseGuardShield` covers only non-streaming responses — streamed chunks
bypass `async_post_call_success_hook` entirely. **Streaming is unprotected in
the baseline.**

## Behavioral invariants to preserve

- **Full message-stack scanning:** `_extract_all_content` (`firewall_callbacks.py:49`)
  joins text from system/developer/user/assistant messages, list-content text
  items, and image URLs.
- **Response extraction:** `_extract_response_content` (`firewall_callbacks.py:79`)
  reads `choices[].message.content` and `reasoning_content`.
- **Generic client error:** every block raises
  `BadRequestError(message="Request blocked by content safety shield.")` with
  `llm_provider` set to the shield name (`BLOCKED_MESSAGE`, `firewall_callbacks.py:39`).
  Client never sees categories or rule detail.
- **Fail mode:** single global `INFERENCE_GATE_FAIL_MODE` env (default `open`),
  read once at import (`firewall_callbacks.py:38`); `closed` re-raises,
  `open` prints and continues (`_handle_shield_error`).
- **Mandatory master key:** `serve.py:70-78` exits if `LITELLM_MASTER_KEY` is
  unset or equals `sk-inference-gate-v1`; key printed only as `************`.
- **Chunking:** Prompt Guard input segmented at 350 words / 50-word overlap /
  512-token truncation (`firewall_callbacks.py:34-36, 96-114`).

## Known baseline defects (inputs to Phase 0 tasks)

1. **Content leaks to stdout/log** — shields `print()` prompt/response material:
   `firewall_callbacks.py:274` (Prompt Guard raw output), `:440` (first 50 chars
   of prompt), `:474` (LlamaGuard raw output), `:711` (first 50 chars of
   response), `:741` (ResponseGuard raw output). `demo.py:454` pipes full proxy
   stdout/stderr to `proxy_debug.log`. (`--detailed_debug` itself was already
   removed.) → task `p0.scrub-debug-logging`.
2. **Dependency drift** — `requirements.txt` is a stale 2026-03-07 hash-pinned
   export; `uv.lock` (litellm 1.82.0) is the real environment. → task
   `p0.dependency-reconcile`.
3. **No live proxy integration test** — everything is import-shimmed unit tests;
   `tests/smoke_test.py` needs real creds. → task `p0.live-proxy-integration-test`.
4. **Module-level side effects** — shield instances are constructed at import
   (`firewall_callbacks.py:534-535, 689, 768`) and `ResponseGuardShield`
   constructs a fresh `LlamaGuardShield()` on every scan (`:724`). Refactor
   target for the control registry (Phase 4), not Phase 0.
5. **`FAIL_MODE` read at import time** — env changes after import have no
   effect; also a single global toggle rather than layered failure policy.
6. **No TLS/CORS** — plain HTTP on `:8001`; no origin policy. → task
   `p0.tls-cors-docs` (docs first, enforcement later).

## Environment variables in current use

`LITELLM_MASTER_KEY`, `LITELLM_API_BASE`, `LITELLM_API_KEY`, `MODEL`,
`LITELLM_CONFIG`, `INFERENCE_GATE_FAIL_MODE`, `LLAMA_GUARD_MODEL`,
`LLAMA_GUARD_API_BASE`, `LLAMA_GUARD_API_KEY`, `LLAMA_PROMPT_GUARD_MODEL`,
`LLAMA_PROMPT_GUARD_API_BASE`, `LLAMA_PROMPT_GUARD_API_KEY`,
`PROMPT_GUARD_LOCAL_MODEL`, `PROMPT_GUARD_LOCAL_THRESHOLD`.
