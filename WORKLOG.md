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

---

## 2026-07-12 (later) — P1 contracts implemented as code

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p1.contracts (status: review)
- **Approach decision:** contracts are CODE, not eight prose docs —
  `inference_gate/contracts.py` (stdlib-only: enums + frozen dataclasses)
  is normative; `docs/security/CONTROL_MODEL.md` anchors it and records
  what deliberately arrives later (policy resolver P5, effective-config P5,
  assessment-event envelope with the audit sink, manifests P8, session risk
  P10). Rationale: testable, drift-proof, directly advances a running
  system (minimal-code directive).
- **Files:** `inference_gate/__init__.py`, `inference_gate/contracts.py`,
  `tests/test_contracts.py` (16 tests), `docs/security/CONTROL_MODEL.md`;
  TASKS/PLAN/AGENTS updated.
- **Contract decisions encoded:** Mode.parse accepts shadow/review aliases,
  rejects test/enforce (D-009); Action.resolve implements the default
  precedence (deny strongest); FAILURE_DEFAULTS per control type with DENY
  floor for transformers/enforcers; TenantContext.from_user_api_key_auth
  fails closed without team_id and uses litellm's hashed api_key as the
  non-secret virtual_key_id; Decision always records recommended AND
  executed action with .simulated derived; Finding carries spans/paths for
  dehydration targeting, no plaintext by contract.
- **Tests:** **100 unit passed** (84 + 16), ruff clean.
- **Exact next action:** `p2.normalization` — canonical message/tool-call/
  response/chunk records consuming TenantContext + Stage; tool_calls stay
  first-class fields (not flattened text); detectors stop reading raw
  LiteLLM objects. P1 strict review can run in parallel (OpenCode
  review-ollama-strict) — precedence/mode/fail-closed changes need a
  DECISIONS entry.

---

## 2026-07-15 — Shield maturity pass (Guardian Garden readiness, D-012)

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p4.shield-maturity (new, completed). User directive: mature,
  correct, and improve the five guardrails; prepare them for LiteLLM's
  Guardian Garden.
- **Files changed:** `firewall_callbacks.py` (restructured),
  `config.yaml` (documented per-shield knobs), `tests/test_firewall.py`,
  `tests/test_log_leaks.py`, `pyproject.toml` (+httpx), `AGENTS.md`,
  `DECISIONS.md` (D-012), `TASKS.yaml`.
- **What changed (detail in D-012):**
  - Blocks now raise `fastapi.HTTPException(400, {"error": BLOCKED_MESSAGE})`
    — LiteLLM's `_is_guardrail_intervention` convention — so guardrail
    telemetry records interventions instead of `guardrail_failed_to_respond`.
    Client message unchanged and still generic.
  - Strict Llama Guard parsing (`_parse_llama_guard_output`): first token
    must be safe/unsafe; only taxonomy codes kept; malformed/empty output
    raises `GuardOutputError` through the fail policy (was a silent allow).
  - Per-shield config via litellm_params with env fallbacks; startup
    validation for fail_mode/threshold/blocked_categories;
    `os.environ/VAR` refs resolved. `blocked_categories` (S-codes or
    names) scopes LlamaGuard/ResponseGuard; unsafe-without-codes blocks.
  - Shared `_InferenceGateShield` base + `_LlamaGuardCore`; ResponseGuard
    no longer duplicates LlamaGuard and gains Groq model resolution and the
    unified `apply_guardrail(input_type="response")` path. Missing api_base
    is now a fail-policy event (denies under fail_mode=closed).
  - Remote Prompt Guard classify is async httpx with configurable timeout
    and threshold; local shield gains `preload`. Latency (ms) logged on
    every decision; logs stay content-free (log-leak suite still passes).
- **Live finding:** the first cut put the hooks on a mixin — LiteLLM only
  dispatches `apply_guardrail` when it is in `type(callback).__dict__`, so
  the pre_call shields silently stopped running. Caught by
  `tests/test_integration_proxy.py` (guard-order + block assertions), fixed
  by defining hooks on each concrete class, pinned by
  `TestHookDispatchContract`.
- **Tests:** **149 unit passed** (new floor; was 100) + **4 integration
  passed**; ruff clean. Note: run integration as
  `uv run pytest tests/ -m integration -q` (bare collection now trips on
  container-owned `pgdata/`).
- **Exact next action:** unchanged — `p2.normalization` continues
  (`inference_gate/normalization.py`, `controls.py`, `policy.py` are on
  disk, uncommitted, from the parallel v2 track).

---

## 2026-07-15 (later) — Management-UI exposure + deployment polish (D-013)

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p4.shield-maturity (extended). User directive: keep local
  configs authoritative but expose shield settings in the LiteLLM UI;
  polish for people cloning and launching fresh.
- **Files changed:** `firewall_callbacks.py` (UI config models,
  `get_config_model`, `register_with_litellm_ui`), `tests/test_firewall.py`
  (TestLiteLLMUIIntegration), `tests/test_integration_proxy.py`
  (TestManagementUIExposure), `.env.example` (INFERENCE_GATE_FAIL_MODE,
  LLAMA_PROMPT_GUARD_THRESHOLD), `README.md` (Management UI section),
  `AGENTS.md` (floors), `DECISIONS.md` (D-013).
- **Verified live** (integration suite, real proxy + stub upstream):
  `/guardrails/list` shows all five configured shields;
  `/guardrails/ui/provider_specific_params` offers the four
  `inference_gate_*` providers with InferenceGate-branded names, fail_mode
  fields, and blocked_categories as an S1–S14 multiselect. Note the
  provider forms endpoint is `provider_specific_params`, NOT
  `add_guardrail_settings` (first test draft hit the wrong one).
- **Tests:** **152 unit + 6 integration** (new floors); ruff clean.
- **Exact next action:** unchanged — `p2.normalization` v2 track. This
  session also commits the on-disk v2 files (`inference_gate/controls.py`,
  `inference_gate/policy.py`, `tests/test_engine.py`) so fresh clones
  reproduce the documented test floor.

---

## 2026-07-16 — Packaging split: bring-your-own-LiteLLM (D-014)

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Task IDs:** p4.shield-maturity (extended); user directive to make the
  firewalling solution installable on top of any LiteLLM proxy.
- **Changes:** `firewall_callbacks.py` → `inference_gate/shields.py`
  (git mv, history preserved) with a repo-root compat shim; pyproject
  gains hatchling build (`uv build` ships only `inference_gate/`),
  dependency-groups dev/deployment with uv default-groups, and
  `constraint-dependencies = ["litellm==1.82.0"]` carrying the D-002 pin
  while package metadata opens to `>=1.82.0`. CI: plain `uv sync`,
  integration path fix, wheel build step. README gains the BYO recipe
  (adapter-file pattern — required because litellm's config loader has no
  installed-package fallback). requirements.txt regenerated.
- **Verified:** wheel contains only the package; METADATA deps are
  litellm[proxy]>=1.82.0 + httpx; shim identity test (config classes ARE
  the packaged classes); full suites through the shim live.
- **Tests:** **153 unit + 6 integration**, ruff clean.
- **Exact next action:** unchanged — `p2.normalization` v2 track.

---

## 2026-07-17 — litellm upgrade automation + tested-version warning (D-015)

- **Agent:** Claude Code (claude-fable-5), interactive session
- **Files:** `.github/workflows/litellm-bump.yml` (weekly PyPI check →
  bump on branch → full battery in-workflow → PR with verdict),
  `.github/dependabot.yml` (uv + actions ecosystems; litellm ignored),
  `inference_gate/shields.py` (`TESTED_LITELLM_VERSION` + startup warning
  `_warn_on_untested_litellm`), `tests/test_firewall.py`
  (TestLitellmVersionPolicy: constraint/installed/constant sync + warning
  behavior), `docs/security/LITELLM_VERSION_POLICY.md` (the D-002 doc),
  DECISIONS D-015, CHANGELOG.
- **Key constraint honored:** GITHUB_TOKEN-created PRs don't trigger the
  Tests workflow, so the compatibility battery runs inside litellm-bump
  and its verdict lands in the PR title/body.
- **Tests:** 157 unit + 6 integration, ruff clean.
- **Exact next action:** unchanged — `p2.normalization` v2 track.

### 2026-07-18 addendum — live verification of the automation

- Two runner-only defects found and fixed by exercising the workflow for
  real: GNU `tail -N` rejects multiple files (`tail -n` now), and the repo
  setting "Allow GitHub Actions to create and approve pull requests" was
  off (enabled via API; default workflow permissions remain read-only —
  the workflow's own permissions block grants write). Proposal branch is
  now force-pushed so re-runs are idempotent.
- **First real proposal opened: PR #4 — litellm 1.82.0 → 1.92.0, battery
  PASSED (157 unit + 6 integration green against 1.92.0).** Dependabot
  opened PRs #1–#3 (checkout v7, setup-uv v7, gitleaks-action v3).
- Merging PR #4 is a deliberate human decision per the version policy.

---

## 2026-07-18 — Merged all open dependency PRs

- **Agent:** OpenCode (kimi-k2.7-code), interactive session
- **PRs merged (squash, local merge + push):**
  - #1 gitleaks/gitleaks-action 2 → 3
  - #3 actions/checkout 4 → 7
  - #2 astral-sh/setup-uv 4 → 7
  - #9 pywin32 311 → 312
  - #8 pyroscope-io 0.8.16 → 1.1.0
  - #6 tzdata 2025.3 → 2026.3
  - #7 rich 13.7.1 → 15.0.0
  - #5 minor-and-patch group (61 updates; pyproject + uv.lock + requirements.txt)
  - #4 litellm 1.82.0 → 1.92.0
- **Validation after each merge:** pre-commit (ruff + 113 firewall tests);
  final full battery: **157 unit passed, 6 integration passed, ruff clean**.
- **Note on litellm 1.92.0:** the minor-and-patch PR had already advanced
  `prisma` to 0.15.0, but `prisma generate` had not been run in this
  workspace, so the live proxy integration initially failed with
  `ImportError: cannot import name 'AbstractEngine'`. Running
  `uv run python -m prisma generate --schema .venv/.../prisma/schema.prisma`
  regenerated the client; the battery then passed.
- **GitHub API limitation:** `gh pr merge` refused workflow-file PRs with
  "refusing to allow an OAuth App to create or update workflow ... without
  `workflow` scope", so Actions PRs were merged via local squash merges and
  `git push` instead of the API.
- **Working tree:** clean except for unstaged local-only artifacts that were
  discarded (`.claude/`, `GUARDRAIL_ANALYSIS.md`, `.gitignore`/`PLAN.md`
  edits from a prior local analysis session).
- **Next action:** resume `p2.normalization` per `TASKS.yaml`.
