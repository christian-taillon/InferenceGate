# DECISIONS.md — Architecture Decision Records

Lightweight ADRs for the InferenceGate v2 transformation. Append new entries;
mark superseded ones rather than deleting them.

Statuses: `proposed` · `accepted` · `superseded` · `rejected`

---

## D-001 — Verified test baseline is 78, not 39

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** PLAN.md Phases 4–5 and the transformation brief cite a 39-test
  baseline. Direct verification (`uv run pytest tests/test_firewall.py -q`)
  shows 78 passing tests (55 functions, parametrized), ruff clean.
- **Decision:** 78 passing tests is the recorded regression floor. All parity
  gates (especially Phase 4 `legacy-default`) measure against 78.
- **Alternatives:** trust prior docs (rejected — empirically wrong).
- **Consequences:** none negative; prevents silently accepting test loss.

## D-002 — uv.lock is the single dependency source of truth; pin LiteLLM ==1.82.0

- **Status:** accepted (implementation pending, task `p0.dependency-reconcile`)
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** Three dependency declarations exist: `pyproject.toml` (ranges,
  `litellm[proxy]>=1.82.0`), `uv.lock` (exact, litellm 1.82.0 — what actually
  runs), and `requirements.txt` (stale 2026-03-07 hash export). CI and
  developers use `uv sync`. The brief requires pinning an exact supported
  LiteLLM version.
- **Decision:** `uv.lock` is authoritative. Change pyproject to
  `litellm[proxy]==1.82.0`; delete `requirements.txt` or regenerate it via
  `uv export` with a "generated — do not edit" header. Version bumps go
  through `docs/security/LITELLM_VERSION_POLICY.md` once it exists.
- **Security consequences:** removes the risk of prod installing different
  (older, unpatched or newer, unvetted) versions than what was tested.
- **Compatibility consequences:** upgrades become deliberate, tested events.

## D-003 — File-based work-state system (AGENTS/PLAN/TASKS/WORKLOG/DECISIONS)

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** Development will span multiple agents (OpenCode autopilot-codex
  orchestrating workers) and sessions. Conversation history is not durable.
- **Decision:** Repository files are the sole source of progress truth:
  `AGENTS.md` (operating manual), `PLAN.md` (roadmap, history preserved),
  `TASKS.yaml` (machine-readable state, `next_task` authoritative),
  `WORKLOG.md` (append-only journal), `DECISIONS.md` (ADRs),
  `GAP_ANALYSIS.md` (behavior vs target), `docs/security/` (designs + reports).
  Existing PLAN.md/GAP_ANALYSIS.md are extended, never replaced.
- **Consequences:** small per-session overhead; any agent can resume cold.

## D-004 — Empirically verify LiteLLM hook dispatch before building the adapter

- **Status:** accepted — **core question resolved 2026-07-12** by source
  reading of installed litellm 1.82.0 (see
  `docs/security/LITELLM_INTEGRATION.md`): `mode: pre_call` +
  `apply_guardrail` dispatches through `UnifiedLLMGuardrails` and **can
  mutate the request** (texts written back into messages) → dehydration is
  viable at pre_call. Our `async_moderation_hook` implementations are dead
  code at 1.82.0 (removal deferred to P4 parity migration). Live proxy trace
  remains in `p05.capability-matrix` as confirmation, no longer a blocker.
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** `config.yaml` declares `mode: "pre_call"` for the custom
  shields, but the shield classes implement `async_moderation_hook` and
  `apply_guardrail` — not `async_pre_call_hook`. Which hook LiteLLM 1.82.0
  actually dispatches (and whether it can mutate the request, which
  dehydration requires) is undetermined. `async_moderation_hook` historically
  runs in parallel with the LLM call and cannot transform the request —
  if that is the live path, **dehydration cannot be a moderation hook**.
- **Decision:** Task `p05.capability-matrix` must include a live-proxy hook
  trace before any control-engine code targets a hook. Transformers
  (dehydration) must run in a hook that executes before provider dispatch and
  can mutate `data` (expected: `async_pre_call_hook`); verify, don't assume.
- **Security consequences:** prevents building dehydration on a hook that
  cannot actually stop plaintext from reaching the provider.

## D-005 — Streaming is unprotected in the baseline; treat as its own boundary

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** `ResponseGuardShield` uses `async_post_call_success_hook` only.
  Streamed responses reach the client chunk-by-chunk without response-side
  scanning. README/docs do not currently claim streaming protection.
- **Decision:** Do not claim streaming protection anywhere until chunk-boundary
  leak tests pass. Interim posture for sensitive profiles: buffer-complete or
  disable streaming. Evaluate `async_post_call_streaming_iterator_hook` at
  1.82.0 during Phase 0.5.
- **Update 2026-07-12 (p05 verification):** native streaming guardrail mode
  confirmed unsafe for enforcement — it samples every 5th chunk and yields
  chunks to the client before inspection; litellm's own comment: "Response
  already started ... cannot send 400". `buffer_then_release` must be built
  as our own iterator on that hook (see LITELLM_CAPABILITY_MATRIX.md).
- **Consequences:** honest security posture; streaming work lands in Phase 12
  with explicit tests (prefix split, JWT split, placeholder split, UTF-8
  boundaries, mid-stream provider failure).

## D-006 — Detection/enforcement separation is the core architectural axiom

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** Current shields couple detection to blocking (each raises
  `BadRequestError` directly). Target architecture: detectors identify facts,
  policy determines meaning, transformers modify data, enforcers act.
- **Decision:** All new controls emit normalized findings; only the decision
  engine maps findings to actions; only enforcers execute them. Legacy shields
  get wrapped as adapters in Phase 4 (`legacy-default` profile reproduces
  today's block behavior through policy, proving the separation).
- **Consequences:** same detection can log/dehydrate/quarantine/confirm/block
  depending on tenant/stage/mode; enables observe→simulate→block rollouts.

## D-007 — AEAD via the `cryptography` package; no custom crypto

- **Status:** proposed (approve when Phase 8 opens)
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** Dehydration manifests need authenticated encryption of original
  secret bytes plus keyed fingerprints (HMAC-SHA256, tenant/scope-derived keys).
- **Decision (proposed):** use `cryptography`'s AESGCM or ChaCha20Poly1305 for
  manifests and `hmac`/`hashlib` stdlib for fingerprints; per-tenant key
  derivation via HKDF. `cryptography` is already in the dependency tree
  (transitively via litellm[proxy]) — pin it directly when Phase 8 starts.
- **Licensing consequences:** Apache-2.0/BSD — compatible.

## D-008 — All guard models are optional, capability-verified, pluggable backends

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** The gateway must support customer-supplied local or hosted
  guard providers: Llama Prompt Guard 2 (22M/86M), Llama Guard 3 (1B/8B),
  Granite Guardian 4.1 8B, gpt-oss-safeguard (20B/120B) — each optional.
  Full spec: `docs/security/GUARD_MODELS.md`.
- **Decision:**
  1. The gateway is fully functional with **zero** guard models
     (deterministic-only). No control-engine code path may assume a guard
     backend exists.
  2. Guard backends plug in through a provider registry keyed by *verified
     capability*, not model name. Registration runs the 14-fixture battery;
     any feature the provider hasn't demonstrated is disabled for it.
  3. Deterministic controls remain authoritative for facts; a guard judgment
     can never grant permission deterministic policy denied (extends D-006).
  4. Model-native outputs are parsed strictly per backend (Llama Guard
     `safe`/`unsafe\nS-codes` only; Granite exactly one `<score>` with
     declared criterion polarity; gpt-oss strict JSON
     allow/violation/review). Malformed output is a failure-policy event,
     never repaired silently; missing scores are null, never fabricated.
  5. Default escalation ladder: deterministic → Prompt Guard → Llama Guard /
     Granite no-thinking → gpt-oss-safeguard 20B → human review / 120B
     offline. 120B is never a default inline guard.
  6. Chain-of-thought/reasoning is never shown to end users and retained
     only under explicit encrypted, access-controlled, DLP'd, short-TTL
     configuration.
- **Alternatives:** mandatory bundled guard stack (rejected — deployment
  weight, licensing variance, contradicts configurability requirement);
  name-based capability assumptions (rejected — providers/templates diverge).
- **Security consequences:** capability verification prevents phantom
  protection (e.g., assuming output classification a runtime doesn't do);
  strict parsers close the "guard output as injection vector" path.
- **Operational consequences:** provider registry + fixture battery is new
  scope in P4 (task `p4.guard-registry`); Granite and gpt-oss backends are
  net-new reviewers.

## D-009 — Canonical rollout modes absorb the guard-spec lifecycle vocabulary

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (workspace prep)
- **Context:** The v2 spec defines rollout modes
  `disabled/observe/alert/simulate-block/confirm/block`; the guard
  orchestration spec uses `disabled/test/shadow/review/enforce`. Two mode
  vocabularies in one policy engine would be ambiguous.
- **Decision:** The v2 set stays canonical. Mapping: `test` → offline fixture
  evaluation (not a runtime mode); `shadow` → `observe`; `review` → `alert`
  with approval-queue sink, or `confirm` when gating; `enforce` →
  `simulate-block`/`confirm`/`block` per action mapping. Config loaders may
  accept the guard-spec aliases and normalize them.
- **Consequences:** one mode enum in schemas/telemetry; guard-spec-authored
  profiles remain readable via aliasing.

## D-010 — System-first sequencing: core pipeline before enterprise tooling

- **Status:** accepted (user directive, 2026-07-12)
- **Context:** External research (merged 2026-07-12, see WORKLOG) ranked the
  work: Presidio and request logging are low/medium difficulty; true tenant
  isolation, central administration, streaming enforcement, and tool/agent
  session assessment are the hard problems. The user directed: get the
  system running first; enterprise tools later.
- **Decision:** Near-term priority is the running core pipeline
  (P0.5 → P1 contracts → P2 normalization → P4 adapters → P5 engine).
  Explicitly deferred until the core runs: OIDC control-plane auth, SAML
  (never self-implemented — identity broker presents OIDC to us), central
  administration, budgets/RBAC UI. Central administration, when it comes,
  is **API-first**: versioned API + declarative YAML; a UI is a later client
  of the same API. Streaming enforcement, tool-call interception, and
  session-level risk stay on the roadmap as the genuinely specialized
  problems (P5/P10/P12) — not enterprise trimming, core security.
- **Consequences:** P11/P12 scope grows (OIDC claim→tenant mapping,
  assessment-event retention per tenant); nothing in P1–P5 may depend on
  enterprise features existing.

## D-011 — Presidio adopted as an optional PII assessment engine

- **Status:** accepted
- **Date:** 2026-07-12 · **Agent:** claude-code (from merged research)
- **Context:** LiteLLM 1.82.0 ships a native Presidio guardrail
  (`proxy/guardrails/guardrail_hooks/presidio.py` — verified installed)
  supporting pre/during/post/logging_only modes against external Presidio
  Analyzer/Anonymizer services.
- **Decision:** Adopt LiteLLM's Presidio integration as one more **optional**
  detector/transformer backend behind the same control abstraction (D-008
  applies: capability-verified, zero-required). Presidio's *masking* remains
  distinct from InferenceGate dehydration: reversible tokenization with
  rehydration authority stays InferenceGate-owned (P8/P9); Presidio may
  detect and irreversibly redact, but must not become a second rehydration
  path. Entity-level policy (block/mask/report/allow per entity, per stage)
  is decided by the InferenceGate policy engine, not Presidio config.
  Double-masking across engines is resolved by finding-overlap resolution
  (P7).
- **Consequences:** new task `p4.presidio-backend`; capability matrix (p05)
  records the verified mode support; deployment needs the two Presidio
  services only for tenants that enable it.

## D-012 — Shield maturity pass: HTTPException blocks, strict guard parsing, per-shield config

- **Status:** accepted
- **Date:** 2026-07-15 · **Agent:** claude-code (user directive: mature the
  guardrails for LiteLLM Guardian Garden membership)
- **Context:** The five-shield pipeline had demo-era rough edges: blocks
  raised `litellm.BadRequestError` (logged by LiteLLM as
  `guardrail_failed_to_respond`, not an intervention); Llama Guard output
  was parsed leniently (`"unsafe" in verdict` — a degraded guard model that
  answers prose silently *allowed* traffic); all configuration was
  env-var-only and global; `ResponseGuardShield` missed the Groq model
  resolution and duplicated LlamaGuard code; hooks were dispatched through
  a mixin that LiteLLM's `type(callback).__dict__` check cannot see (caught
  live by the integration suite — inherited hooks silently never run).
- **Decision:**
  1. Policy blocks raise `fastapi.HTTPException(status_code=400,
     detail={"error": BLOCKED_MESSAGE})` — the convention LiteLLM
     recognizes as a guardrail *intervention* in
     `StandardLoggingGuardrailInformation` and metrics. Message stays
     generic (no shield names, labels, scores, or S-codes to clients).
  2. Llama Guard output is parsed strictly (first token exactly
     `safe`/`unsafe`; only taxonomy codes kept). Malformed output raises
     `GuardOutputError` and routes through the fail policy — a fail-policy
     event, never a silent allow (aligns with D-008 §4 ahead of P4).
  3. Every shield accepts `litellm_params` config (api_base, api_key,
     model, fail_mode, threshold, blocked_categories, timeout, preload)
     with the legacy env vars as fallbacks; invalid config (bad fail_mode,
     out-of-range threshold, unknown category) fails at proxy startup.
  4. `blocked_categories` scopes which S1–S14 categories block; an unsafe
     verdict without a recognizable category always blocks (deny by
     default). Missing api_base is now a fail-policy event too (deny when
     fail_mode=closed, was silently skipped).
  5. Hook methods are defined on every concrete shield class, pinned by a
     dispatch-contract test; `ResponseGuardShield` gained the unified
     `apply_guardrail(input_type="response")` path and shares
     `_LlamaGuardCore` with `LlamaGuardShield` (Groq resolution bug fixed
     by construction).
- **Alternatives:** keep BadRequestError (rejected — misclassified in
  guardrail telemetry); lenient guard parsing (rejected — silent allow on
  guard degradation is a bypass); config-only via env (rejected — Guardian
  Garden guardrails are configured per-instance in config.yaml).
- **Consequences:** unit floor rises 100 → 149; P4 adapter work inherits a
  clean per-shield config surface; the `legacy-default` parity target now
  includes the strict-parse fail-policy semantics.

## D-013 — Management-UI exposure via litellm's guardrail registries

- **Status:** accepted
- **Date:** 2026-07-15 · **Agent:** claude-code (user directive: manage local
  configs, expose things in the UI as well)
- **Context:** The LiteLLM dashboard builds its Add Guardrail provider list
  dynamically from `/guardrails/ui/provider_specific_params`, which iterates
  `guardrail_class_registry` and renders each provider's
  `get_config_model()` pydantic fields as typed forms (verified in the
  1.82.0 UI bundle: the provider map merges endpoint keys via
  `ui_friendly_name`). Config-file guardrails are listed but not editable
  in the UI; DB-created guardrails initialize through
  `guardrail_initializer_registry` or a dotted `guardrail:` path.
- **Decision:**
  1. Each shield implements `get_config_model()` returning a
     `GuardrailConfigModel` subclass (api_base/api_key/model/fail_mode plus
     shield-specific knobs; `blocked_categories` renders as an S1–S14
     multiselect).
  2. `register_with_litellm_ui()` inserts the four shields into
     `guardrail_class_registry` and `guardrail_initializer_registry` under
     `inference_gate_*` provider names at import time — best-effort with
     `setdefault` and a logged no-op if litellm's internals move (the
     version is pinned; upgrades revalidate via the integration test).
  3. Division of authority: `config.yaml` remains the source of truth for
     the default pipeline; UI-created guardrails are DB-managed additions.
     At least one `firewall_callbacks.*` reference must remain in
     config.yaml — importing the module is what performs registration.
- **Alternatives:** UI-only management via DB guardrails (rejected — the
  pipeline must be reviewable/versionable config); no UI exposure
  (rejected — user requirement).
- **Consequences:** integration suite gains UI-endpoint assertions
  (providers present, category multiselect rendered); unit floor 152 + 6
  integration. Registry mutation is the one deliberate dependency on
  litellm-internal layout — guarded, tested, and pinned.
