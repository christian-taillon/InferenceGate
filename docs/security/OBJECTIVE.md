# InferenceGate v2 — Target Specification

Condensed, durable statement of the transformation objective. This is the
in-repo source of truth for *what* is being built; `PLAN.md`/`TASKS.yaml`
track *where we are*; `docs/security/reports/legacy-baseline.md` records
*what existed before*.

## Mission

Evolve InferenceGate from a fixed five-shield LiteLLM guardrail demo into an
enterprise, multi-tenant, policy-driven LLM security gateway, while preserving
existing behavior (78-test baseline) behind a `legacy-default` compatibility
profile.

**Primary security objective:** AI agents can reason about, reference, move,
and reuse *typed sensitive-data variables* without ordinarily receiving the
underlying plaintext. Detection observes; policy interprets; dehydration
converts secrets to scoped placeholders; rehydration happens only at
authorized execution boundaries; re-dehydration keeps returned data safe.

## Core axiom (D-006)

> Detectors identify facts. Classifiers and reviewers add context.
> Policy determines what those facts mean. Transformers modify data.
> Enforcers carry out decisions.

No detector is inherently coupled to blocking. The same credential detection
may log in a test, dehydrate in a prompt, quarantine in retrieved content,
require approval in a tool call, block in a response, or add risk to a
correlation chain — depending on tenant, app, key, user, route, model,
provider, stage, source, destination, confidence, severity, session behavior,
and rollout mode.

## Control types

`normalizer` · `decoder` (bounded base64/hex/URL/unicode/HTML-entity views,
strict depth/size/expansion limits) · `detector` (deterministic findings:
Telltale rules, secret signatures, PII, SQLi, tool misuse) · `classifier`
(scored label, e.g. Prompt Guard) · `reviewer` (taxonomy/policy judge, e.g.
Llama Guard, human approval) · `correlator` (cross-event chains: secret access
→ egress, injection → tool execution) · `transformer` (dehydrate, redact,
drop field, quarantine, label untrusted) · `decision_engine` · `enforcer`
(allow/deny/approve/route/drop/quarantine) · `sink` (sanitized metrics,
traces, audit, SIEM).

Classifier/reviewer backends are **optional, customer-supplied, capability-
verified guard models** (D-008): Llama Prompt Guard 2 (22M/86M), Llama Guard 3
(1B/8B), Granite Guardian 4.1 8B, gpt-oss-safeguard (20B/120B). Roster,
selection rules, escalation ladder, strict output parsers, provider
verification battery, and streaming modes: `GUARD_MODELS.md`. The gateway must
run deterministic-only with zero guard models configured.

## Trust-boundary stages

Richer than LiteLLM's pre/post hooks (internal model; hooks are the adapter):

```
ingress.request → request.normalized → request.context → retrieval.content
→ mcp.metadata → pre_provider → provider.response → tool.call.proposed
→ pre_tool_execution → tool.result → model_to_model → client.response
→ storage.egress · control_plane.change
```

## Execution / rollout modes

`disabled → observe → alert → simulate-block → confirm → block`.
Every simulated decision records both `recommended_action` and
`executed_action`. Never jump from development straight to `block`.

## Configuration precedence (lowest→highest)

Product defaults → bundled rule packs → org packs → deployment packs → rule
overrides → allowlists → detection-selection policy → global control profile
→ environment profile → tenant profile → app/virtual-key profile → route
profile → emergency admin override. Request content can never weaken its own
policy. Reloads are atomic: validate → compile → resolve → smoke-test →
activate; partial validity never touches active policy. Every runtime decision
references an effective `configuration_id`.

## Platform invariants (never silently bypassable)

Config validation, tenant authorization, manifest integrity, rehydration
authorization, cross-tenant isolation, AEAD validation, refusal of malformed
rules, atomic activation, no-plaintext-secret logging. Features may be
disabled wholesale; their integrity mechanisms may not be weakened while on.

## LiteLLM ownership boundary

**LiteLLM owns** (adopt native, don't rebuild): provider compatibility,
OpenAI-compatible endpoints, virtual keys/users/teams/orgs, budgets, TPM/RPM,
model access groups, routing/load-balancing/retries/fallbacks, cost
accounting, static MCP server/tool authorization, lifecycle hooks,
Prometheus/OTel, admin APIs, provider credential references.

**InferenceGate owns:** Telltale detection semantics, trust-boundary stages,
normalized findings, secret/PII/prompt-injection interpretation, correlation,
enterprise control policy, transformations, approvals, destination-sensitive
tool policy, dehydration/rehydration, security audit semantics, policy
simulation/explanation.

LiteLLM Guardrail Policies / Flow Builder may be *deployment adapters* only —
never the canonical policy format. Normalize LiteLLM identity into a security
context (`tenant_id`, `organization_id`, `user_id`, `virtual_key_id` [non-secret
identifier], `application_id`, `environment`); never place a raw virtual key in
findings/manifests/logs.

**Pinned version:** litellm[proxy] **1.82.0** (uv.lock; D-002). Version changes
go through `LITELLM_VERSION_POLICY.md`. Verify hook behavior empirically at
this version (D-004) — notably whether `mode: pre_call` on a `CustomGuardrail`
dispatches `async_pre_call_hook` vs `async_moderation_hook` vs
`apply_guardrail`, and which of those can *mutate* the request (dehydration
requires mutation before provider dispatch).

## Telltale compatibility

- References: https://github.com/Dark-Roast-Cyber/telltale (Apache-2.0),
  detection catalog at https://agentarchaeology.ai/telltale/detection-catalog/
- Pin an exact Telltale commit for conformance; record in
  `telltale_compatibility: {repository_commit: <FULL_SHA>}`.
- A Telltale rule file must load in both products without rewrite. Mirror the
  actual schema/loader/modifiers/overrides/allowlists/policy filtering;
  document every intentional incompatibility.
- Directory concepts: `rules.d/ overrides.d/ policies.d/ allowlists.d/` plus
  gateway-only `extraction.d/ control-profiles.d/`. Portable rules describe
  *observations*; control profiles describe *placement and action*. Never mix.
- Telltale `category` stays behavior-oriented (secret_access, execution,
  exfiltration, …). Secret *semantic* categories (token, key_material,
  connection_string, …) live in extraction sidecar metadata.
- Build a cross-product conformance suite (IDs, categories, severity, targets,
  spans, modifiers, allowlists, invalid-rule behavior) over shared fixtures.

## Secret ruleset licensing (hard constraint)

Approved sources only, pinned by commit in `config/security/sources.lock.yaml`
with `THIRD_PARTY_NOTICES.md` + `licenses/`:
Telltale (Apache-2.0), Gitleaks (MIT), Titus (Apache-2.0), Yelp detect-secrets
(Apache-2.0), Secretlint (MIT), Nosey Parker (Apache-2.0, legacy-only, not an
independent source vs Titus). **Excluded:** TruffleHog (AGPL), DataSentry
(GPL), Semgrep community rules, unknown-license repos, blog content, leaked
secrets, breach or customer data. Candidates go through a machine-readable
inventory with provenance → multi-level dedup (textual, structural, semantic,
subsumption, runtime) → review → 50–100 rule high-signal pilot pack. Every
production rule: stable ID, ≥3 synthetic positives, ≥5 realistic negatives,
FP notes, provenance, portable-regex validation, conformance.

## Dehydration

- Placeholder: `{{inference-gate:<scope-ns>:<category>-<signature>-<ordinal>}}`.
  Contains no secret bytes, length, unkeyed hash, tenant ID, or destination.
- Scopes: `document | request | session | bundle` (default request; session
  when a trustworthy session ID exists). Same secret in scope → same
  placeholder; no globally correlatable cross-tenant IDs.
- Fingerprint: HMAC-SHA256 with tenant/scope-derived key (never plain SHA-256);
  fingerprints never reach models or general logs.
- Protected manifest per operation: IDs, tenant, scope, timestamps/TTL,
  placeholder metadata, finding refs, source path+span, keyed fingerprint,
  AEAD-encrypted original bytes, key ID, authorization restrictions,
  revocation state. Storage abstraction: in-memory ephemeral + encrypted
  persistent, TTL, revocation, tenant isolation, key rotation. No custom
  crypto (D-007).
- Replacement engine: resolve overlaps first, replace only the sensitive
  value, preserve syntax and JSON types, right-to-left in text spans,
  deterministic and idempotent, recognizes its own placeholders, never puts
  plaintext in exceptions.

## Rehydration

Only at `pre_tool_execution` (or another explicitly authorized execution
boundary). Modes: `disabled | trusted_tool_only (default) | approved_fields |
full`. A placeholder is honored only when the manifest exists, namespace/
tenant/scope/session match, unexpired, unrevoked, destination+field+tool
authorized, integrity valid. Placeholder-*shaped* input is never rehydrated
(placeholder-injection defense; test guessed ordinals, cross-tenant/session
reuse, modified category/signature, expired/missing manifests, prompt
requests for restoration). Destination policy restricts fields, secret
categories, and hosts per tool. Everything returning toward a model (tool
results, shell/HTTP output, errors, stack traces) is re-scanned and
re-dehydrated, reusing the existing placeholder for a returning secret.

## Failure policy (layered, replaces global INFERENCE_GATE_FAIL_MODE)

Defaults: detector/classifier/reviewer error → `allow_and_alert`;
transformer/manifest/rehydration/output-scan error → `deny`. Stage overrides
allowed (e.g. `pre_provider.final_dlp_error: deny`,
`pre_tool_execution.any_error: deny`). Tenant-resolution failure denies.
Cryptographic/auth/tenant-isolation/manifest failures cannot be downgraded by
an LLM reviewer.

## Telemetry and audit

Controls emit only safe DTOs (control_id, stage, verdict, action, categories,
rule_ids, counts, latency, policy/config IDs) — never the LiteLLM request/
response object. Raw pre-dehydration content must not reach spend logs, prompt
logs, cache keys/values, OTel attributes, or provider debug output. Audit
records: who/when/tenant, config ID, policy, control, stage, rule IDs,
recommended vs executed action, approval result, tool identity, destination
class, reason codes — no plaintext, prompts, responses, manifests, or HMACs.

## Streaming (D-005)

A separate security boundary. Unprotected in the baseline. Options: buffer
complete output, disable streaming under sensitive controls, or a tested
rolling buffer with delayed emission via the streaming iterator hook. Claim
protection only after chunk-boundary tests pass (split prefixes/JWTs/
private-key headers/placeholders, UTF-8 boundaries, mid-stream failure).

## Multi-tenancy

LiteLLM virtual keys/teams/orgs are the identity backbone. InferenceGate adds
tenant-scoped policy, overrides, provider allowlists, reviewer permissions,
manifest isolation, per-tenant fingerprint keys and encryption context, audit
ownership. Negative tests: tenant A cannot resolve B's placeholders, read B's
manifests, share cache entries, or appear in B's telemetry; identical secrets
across tenants yield uncorrelatable IDs.

## Legacy migration map (Phase 4)

| Existing | Becomes |
|---|---|
| `litellm_content_filter` (`inference-gate`) | deterministic detector adapter |
| `LlamaPromptGuardShield` (remote) | prompt-injection classifier backend |
| `PromptGuardLocalShield` | alternate backend, same logical classifier |
| `LlamaGuardShield` | content-safety reviewer |
| `ResponseGuardShield` | reviewer at `provider.response` |
| generic `BadRequestError` | client-safe enforcement adapter |
| `INFERENCE_GATE_FAIL_MODE` | legacy failure-policy adapter |
| `_extract_all_content` | normalization adapter seed |
| master-key checks | platform invariant |

Old config support stays until parity tests pass; provide translator,
deprecation warnings, migration docs, rollback path.

## Suggested code layout (adapt, don't force)

`inference_gate/` package: `integration/litellm.py`, `normalization/`,
`controls/`, `detection/` (incl. `telltale/`, `secrets/`, `pii/`,
`decoding/`), `classifiers/`, `reviewers/`, `policy/`, `actions/`,
`dehydration/`, `rehydration/`, `telemetry/`, `configuration/`.
`firewall_callbacks.py` ends as a thin adapter. **No big file moves before
baseline + compatibility tests exist.**

## Review gates

- **Rule gate:** stable ID, category, rationale, fixtures, FP notes,
  provenance, portable regex, conformance, changelog entry.
- **Control gate (enforcement mode):** unit + integration tests, timeout and
  failure behavior, metrics, safe errors, no-secret-logging tests, tenant
  tests, first-pass + strict review.
- **High-risk changes** (rehydration, new destinations, external reviewers,
  auto-block, weakened DLP, tenant keys, manifest persistence, plugins,
  streaming release): strict review + DECISIONS.md entry required.

## OpenCode agent roster (delegation cheat-sheet)

- `autopilot-codex` (openai/gpt-5.5) — orchestrator; architecture, security
  decisions, schema approval, final acceptance.
- `explore` (gpt-5.4-mini) — read-only repo mapping.
- `planner-ollama` (glm-5.2) — advisory planning.
- `search-ollama` (deepseek-v4-flash) / `contained-net-research` — docs and
  upstream-repo research; no private data.
- `coder-ollama` (kimi-k2.7-code) — well-specified implementation (importers,
  validators, fixtures, CLI, docs) with explicit file ownership.
- `general-lite-ollama` (nemotron-3-super) — repetitive low-risk work; never
  architecture/security decisions.
- `coder-codex` (gpt-5.5 high) — control engine, LiteLLM lifecycle, crypto,
  concurrency, multi-tenant isolation, streaming, rescue of failed work.
- `review-ollama` → `review-ollama-strict` (glm-5.2) → `escalation`
  (gpt-5.5 high) — review ladder.
- Never `yolo`. No concurrent edits to the same file; explicit task IDs from
  TASKS.yaml; workers report files/commands/tests/decisions; orchestrator
  reviews every diff; sequential handoffs over swarms.

## Acceptance criteria (abbreviated — full list in original brief)

Baseline preserved & recorded · work state in repo files · policy-driven
control graph · detection ≠ enforcement · LiteLLM-native identity/routing
reused · Telltale rules portable across products · pinned licensed sources
only · dehydrated placeholders reach providers · placeholder reuse in scope ·
no cross-tenant correlation · rehydration only at authorized boundaries ·
tool output re-dehydrated · no plaintext in logs/traces/spend/caches ·
streaming leak-safe or disabled · observe/simulate before enforce · decisions
reference config version · multi-tenant negative tests pass · CI secret
scanning · debug logging gated · TLS documented · version/supply-chain policy
documented · all remaining gaps explicitly recorded · resumable from repo
files alone.
