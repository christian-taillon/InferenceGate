# WORKLOG.md — Append-only work journal

Never rewrite or delete prior entries. Newest entry last.

---

## 2026-07-12 — Workspace preparation for the v2 transformation

- **Agent:** Claude Code (claude-fable-5), interactive session (pre-OpenCode prep)
- **Task IDs:** p0.capture-baseline, p0.workstate-files
- **Repository state at start:** branch `main`, HEAD `784bb21`, clean tree
  (untracked `.claude/` only), 2 unpushed local commits ahead of `origin/main`.
- **Files inspected:** PLAN.md, GAP_ANALYSIS.md, config.yaml,
  firewall_callbacks.py, serve.py, demo.py (debug paths), pyproject.toml,
  uv.lock (litellm pin), .github/workflows/test.yml, .gitignore, tests/,
  scripts/.
- **Files changed (all new, no existing files modified except listed):**
  - `AGENTS.md` (new) — agent operating manual
  - `TASKS.yaml` (new) — machine-readable task state, phases p0–p13
  - `DECISIONS.md` (new) — ADRs D-001…D-007
  - `WORKLOG.md` (new) — this file
  - `docs/security/OBJECTIVE.md` (new) — condensed target specification
  - `docs/security/reports/legacy-baseline.md` (new) — verified baseline
  - `PLAN.md` (extended) — added "Transformation Program (v2)" section; history preserved
  - `GAP_ANALYSIS.md` (updated) — corrected statuses now stale after Phase 6
    (gitleaks CI, response scanning, message scope, master key, error detail)
- **Commands run:** `git status`, `git log`, `uv run pytest tests/test_firewall.py -q`,
  `uv run ruff check .`, greps over demo.py/uv.lock.
- **Tests run / results:** **78 passed** (~1.2s); ruff **clean**.
- **Decisions made:** D-001 (78-test baseline supersedes "39"), D-002 (uv.lock
  authoritative; pin litellm ==1.82.0), D-003 (file-based work state),
  D-004 (verify hook dispatch before adapter work — moderation hooks may not
  be able to mutate requests, which dehydration requires), D-005 (streaming is
  unprotected in baseline; own boundary), D-006 (detection/enforcement
  separation axiom), D-007 proposed (AEAD via `cryptography`).
- **Problems encountered:**
  - Prior docs' "39 tests" figure is stale (actual 78).
  - GAP_ANALYSIS.md predates Phase 6 hardening — several ❌ items were
    already fixed (gitleaks CI, master-key enforcement, response scanning,
    full-stack scanning, generic errors, fail-mode toggle).
  - `--detailed_debug` already removed, but shields still `print()` content
    excerpts and demo.py pipes proxy stdout to `proxy_debug.log`.
- **Remaining risks:** hook-dispatch ambiguity (D-004) could invalidate the
  planned transformer placement — resolve in p05 before writing engine code;
  streaming leak path open until Phase 12.
- **Exact next action:** task `p0.scrub-debug-logging` — replace shield
  `print()` calls with content-free structured logging, gate demo.py's
  `proxy_debug.log` capture behind `INFERENCE_GATE_DEV_DEBUG=1`, add
  `tests/test_log_leaks.py`. Then `p0.dependency-reconcile`.

---

## 2026-07-12 (later) — Guard-model orchestration integrated into the plan

- **Agent:** Claude Code (claude-fable-5), interactive session (workspace prep)
- **Task IDs:** plan integration (no code); created task `p4.guard-registry`
- **Context:** User supplied the "Guard Model Orchestration Instructions"
  spec and directed that all guard models be supported **optionally**.
- **Files changed:**
  - `docs/security/GUARD_MODELS.md` (new) — condensed orchestration spec:
    roster (Prompt Guard 2 22M/86M, Llama Guard 3 1B/8B, Granite Guardian 4.1
    8B, gpt-oss-safeguard 20B/120B — every one optional; deterministic-only is
    a valid deployment), selection/escalation rules, per-model strict output
    parsers and cautions, provider capability verification (14-fixture
    battery), failure actions, streaming modes, normalized guard DTO,
    lifecycle-mode mapping, default + low-resource configurations, legacy
    shield mapping.
  - `DECISIONS.md` — added D-008 (guard models optional/capability-verified/
    pluggable; strict parsers; escalation ladder; no CoT exposure) and D-009
    (canonical v2 mode set absorbs guard-spec lifecycle vocabulary via
    aliasing: shadow→observe, review→alert/confirm, enforce→simulate/confirm/
    block; test = offline fixtures).
  - `TASKS.yaml` — new task `p4.guard-registry` (registry + capability
    battery + strict parsers + normalized DTO); notes added to
    `p4.legacy-migration` (backend strategies, tightened LlamaGuard parsing),
    `p5.decision-engine` (escalation ladder, mode aliasing, trust-aware
    actions), `p10.agent-security` (Granite RAG quality criteria and
    tool-call conversation-support check).
  - `PLAN.md` — P4/P5 phase-table rows expanded; key implementation note #7.
  - `docs/security/OBJECTIVE.md` — control-types section now references the
    optional guard-model roster and GUARD_MODELS.md.
- **Decisions made:** D-008, D-009.
- **Tests run:** none required (docs/state only); TASKS.yaml re-validated
  with yaml.safe_load.
- **Remaining risks:** Granite Guardian and gpt-oss-safeguard backends are
  net-new implementation scope (parsers, criterion polarity, policy packs) —
  sized into P4/P5/P10; provider registry transport vs LiteLLM router overlap
  to be resolved in `p05.capability-matrix`.
- **Exact next action:** unchanged — `p0.scrub-debug-logging`.

---

## 2026-07-12 (later) — P0 development: log scrub, dependency pin, hook-dispatch resolution

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p0.scrub-debug-logging (completed), p0.dependency-reconcile
  (completed), p05.capability-matrix (partially advanced — hook dispatch)
- **Files changed:**
  - `firewall_callbacks.py` — all `print()` replaced with
    `logging.getLogger("inference_gate.shields")`; content-free records only
    (shield, verdict, chunk counts, char lengths, taxonomy-filtered S-codes,
    scores). `_handle_shield_error` logs exception *type* only — exception
    messages may embed payloads. Added `DEFAULT_LLAMA_GUARD_MODEL`;
    `ResponseGuardShield` now resolves its guard model once in `__init__`
    instead of constructing a fresh `LlamaGuardShield()` per scan.
  - `demo.py` — `proxy_debug.log` capture gated behind
    `INFERENCE_GATE_DEV_DEBUG=1`; default pipes proxy output to DEVNULL.
  - `tests/test_log_leaks.py` (new) — 5 tests: no `print(` in shield module;
    fail-open omits exception text; LlamaGuard/ResponseGuard block paths leak
    no canary content; non-taxonomy codes dropped from logs.
  - `pyproject.toml` — `litellm[proxy]==1.82.0`, `openai>=2.26.0,<3`;
    `requirements.txt` regenerated via `uv export`; `uv.lock` re-resolved.
  - `docs/security/LITELLM_INTEGRATION.md` (new) — verified hook dispatch.
  - `CHANGELOG.md` (new).
- **Commands run:** `uv run pytest tests/ -q`, `uv run ruff check .`,
  `uv lock`, `uv export --format requirements-txt -o requirements.txt`,
  `uv sync --extra dev`; extensive grep/read of installed litellm source.
- **Tests run / results:** **83 passed** (78 baseline + 5 new), ruff clean.
- **Decisions made / findings:**
  - **D-004 core resolved by source reading of installed litellm 1.82.0:**
    `mode: pre_call` + `apply_guardrail` → `UnifiedLLMGuardrails.
    async_pre_call_hook` → chat translation handler extracts texts from all
    messages + tool calls, calls `apply_guardrail(input_type="request")`,
    and writes returned texts back into the request. **Request mutation is
    supported at pre_call → dehydration is viable.**
  - Our shields' `async_moderation_hook` methods are dead code at 1.82.0
    (unified routing bypasses them). Deliberately NOT removed yet: they are
    the only callers of `_extract_all_content` (invariant pinned by tests)
    and removal belongs to P4 parity migration after a live trace.
  - `during_call` runs parallel and cannot mutate; streaming iterator hook
    exists in the unified layer (candidate for P12 chunk_guard); litellm has
    per-guardrail Prometheus metrics, guardrail load balancing, and pipeline
    features to evaluate in p05.
- **Remaining risks:** live-proxy confirmation of dispatch still pending
  (p05); message-role coverage of litellm's `_extract_inputs` unverified;
  streaming buffering semantics unknown.
- **Exact next action:** `p0.live-proxy-integration-test` — end-to-end test
  with a stub upstream provider asserting block + pass-through behavior
  through a real running proxy; doubles as the live hook-dispatch trace
  (log hook order from a probe guardrail while at it).

---

## 2026-07-12 (later) — P0 complete: live integration tests, Python pin, TLS/CORS docs

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p0.live-proxy-integration-test (completed), p0.tls-cors-docs
  (completed) → **Phase P0 fully complete**; current phase now p05.
- **Files changed:**
  - `tests/test_integration_proxy.py` (new) — 4 end-to-end tests; boots the
    real proxy against a threaded stub upstream that plays guard + target
    models (no credentials). Asserts: safe pass-through with guard-before-
    provider ordering and response-scan-after; deterministic filter block;
    Llama Guard block with generic message, no S-codes, provider never
    called (live D-004 confirmation); response-guard block without leaking
    the unsafe output.
  - `pyproject.toml` — `[tool.pytest.ini_options]`: `integration` marker,
    default `addopts = -m 'not integration'` (first placement accidentally
    split the optional-dependencies table; fixed by moving to end of file).
  - `.python-version` (new) — pins **3.13**. Root cause: venv had drifted to
    Python 3.14 where uvloop cannot import (`BaseDefaultEventLoopPolicy`
    removed) → the proxy could not start at all on this machine. Rebuilt
    venv with 3.13.
  - `.github/workflows/test.yml` — `uv sync --python ${{ matrix }}` so the
    3.12 leg isn't overridden by .python-version; added integration-test step.
  - `docs/security/OPERATIONS.md` (new) — TLS patterns (ingress-first,
    native flags verified) + **verified CORS limitation**: litellm 1.82.0
    hardcodes `origins=["*"]`, `allow_credentials=True`
    (proxy_server.py:1076), no config knob → enforce at ingress.
  - `docs/security/LITELLM_INTEGRATION.md` — live-confirmation section.
  - `GAP_ANALYSIS.md` — TLS/CORS/integration/leak-test rows updated.
  - `TASKS.yaml`, `CHANGELOG.md` updated.
- **Commands run:** `uv run pytest tests/ -q`, `uv run pytest -m integration
  -q`, `uv python install 3.13`, `uv sync --extra dev`, manual proxy boot for
  diagnosis, litellm source greps (CORS/TLS).
- **Tests run / results:** unit **83 passed**; integration **4 passed**
  (~5s); ruff clean.
- **Problems encountered:**
  - Proxy failed to boot on Python 3.14 (uvloop import error) — fixed via
    .python-version pin, documented in CHANGELOG.
  - First ordering assertion was wrong: it required *all* guard calls before
    the target call, but ResponseGuard legitimately calls Llama Guard after
    the provider. Corrected to min(guard) < min(target) < max(guard).
- **Remaining risks:** integration suite asserts hook *order*, not content
  plumbing (texts batching, roles, multimodal) — that stays in p05.
- **Exact next action:** `p05.capability-matrix` — build
  LITELLM_CAPABILITY_MATRIX.md against installed 1.82.0 (virtual keys,
  teams, spend-log content, streaming iterator buffering, guardrail
  pipelines/load-balancing, secret managers), classifying each capability
  adopt/wrap/build/defer/reject.

---

## 2026-07-12 (later) — External research merged; tool_calls scan gap fixed

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Context:** User supplied external difficulty/architecture research
  (Presidio, audit events, tenant isolation, OIDC/SAML, streaming, tool
  calls, session risk, central admin) with the directive: **get the system
  running first; enterprise tools later.**
- **Code changed:**
  - `firewall_callbacks.py` — `_extract_response_content` now extracts
    `tool_calls` (function names + arguments). Research finding verified
    real: a harmful tool invocation with benign text previously bypassed
    ResponseGuard entirely. New test
    `test_extract_response_content_includes_tool_calls`. **Floor now 84
    unit + 4 integration; ruff clean.**
- **Work-state changes:**
  - `DECISIONS.md` — D-010 (system-first sequencing; enterprise auth/admin
    deferred; SAML never self-implemented, broker→OIDC only; central admin
    API-first) and D-011 (Presidio adopted as optional engine via litellm's
    native guardrail — verified present at 1.82.0
    `proxy/guardrails/guardrail_hooks/presidio.py`; its masking is
    irreversible and never becomes a second rehydration path).
  - `TASKS.yaml` — new `p4.presidio-backend`; p1 notes gained the
    assessment-event fields (trace/session ids, model_requested vs used,
    immutable policy_version, content_hash, redacted_evidence, fail/bypass
    recording, async pipeline); p2 notes record the tool_calls fix and
    first-class tool_call fields; p10 gained session-risk-state notes; p11
    gained tenant hierarchy / trusted-context / OIDC-first / API-first-admin
    notes with "deferred per D-010".
  - `GUARD_MODELS.md` roster gained a Presidio row; `PLAN.md` key note #7
    (system-first) added; AGENTS.md floors updated.
- **Not merged (already covered):** normalized verdict schema (≡ P1
  finding/decision contracts), assessment orchestrator diagram (≡ v2 control
  graph), streaming modes (≡ GUARD_MODELS/D-005), never-trust-request-tenant
  (≡ OBJECTIVE precedence), isolation test list (≡ OBJECTIVE multi-tenancy).
- **Tests:** 84 unit passed; 4 integration passed earlier this session;
  ruff clean.
- **Exact next action:** `p05.capability-matrix` (unchanged). Per D-010 keep
  it lean: verify only what P1–P5 depend on (spend-log content, streaming
  iterator buffering, virtual-key context shape, custom-auth caveats,
  Presidio guardrail modes); defer enterprise feature research.

---

## 2026-07-12 (later) — Committed; P0.5 capability matrix complete

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p05.capability-matrix (completed) → **current phase P1**
- **Commits:** `d0d6558` (work-state system + design docs), `a381644`
  (content-free logging, debug gating, tool_call scanning, leak tests),
  `9336adc` (integration suite, litellm/Python pins, CI). Tree clean;
  nothing pushed.
- **Files changed after commits:**
  `docs/security/LITELLM_CAPABILITY_MATRIX.md` (new), D-005 update in
  `DECISIONS.md`, TASKS/PLAN advanced to P1.
- **Verified findings (installed 1.82.0 source):**
  - **Spend logs are content-free by default** — prompts/responses stored
    only with `store_prompts_in_spend_logs: true` (general_settings or env);
    `turn_off_message_logging` redacts callback payloads
    (spend_tracking_utils.py:879-895).
  - **UserAPIKeyAuth** carries team_id/org_id/user_id/key_alias/end_user_id/
    metadata, and auto-hashes `api_key` in a validator — hooks receive a
    non-secret key identifier (maps directly to our virtual_key_id).
  - **Native streaming guardrails are unsafe for enforcement**: default
    sampling_rate=5 (scan every 5th chunk over accumulated text),
    chunks yielded to the client before inspection; upstream comment admits
    a mid-stream block cannot send an error ("Response already started").
    → buffer_then_release is a build item (P12), attachment point adopted.
  - Presidio guardrail params verified (analyzer/anonymizer bases,
    output_parse_pii, per-entity `pii_entities_config` actions).
  - Model access groups + guardrail load balancing + per-guardrail
    Prometheus metrics confirmed present (adopt/wrap in P4/P11).
- **Deferred per D-010:** LITELLM_DATA_HANDLING/VERSION_POLICY/SUPPLY_CHAIN
  docs (P12), custom-auth caveats (P11).
- **Tests:** unchanged (84 unit + 4 integration, ruff clean) — docs-only
  changes since last run.
- **Exact next action:** `p1.contracts` — write CONTROL_MODEL.md, STAGES.md,
  FINDING_SCHEMA.md, DECISION_SCHEMA.md, ACTION_MODEL.md, POLICY_MODEL.md,
  POLICY_PRECEDENCE.md, FAILURE_POLICY.md in docs/security/, folding in the
  assessment-event fields (p1 task notes) and the UserAPIKeyAuth→tenant
  context mapping (capability matrix consequence #1). Gate: strict
  architecture review before any engine code.
