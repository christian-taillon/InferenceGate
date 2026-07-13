# LiteLLM Capability Matrix — verified at 1.82.0

Task `p05.capability-matrix`. Every entry below was verified against the
**installed** `litellm==1.82.0` package on 2026-07-12 (file references are
into `.venv/.../litellm/`). Scope is lean per D-010: capabilities P1–P5
depend on are verified deeply; deferred enterprise items are marked and left
for later verification. Dispositions: **adopt** (use native) · **wrap**
(native transport, InferenceGate semantics) · **build** (InferenceGate owns)
· **defer** (later phase) · **reject** (do not use for this purpose).

| Capability | Disposition | Verified facts | Notes for our phases |
|---|---|---|---|
| Guardrail hook dispatch (`mode: pre_call` → unified `apply_guardrail`) | **adopt** (attachment point) | Full chain in `LITELLM_INTEGRATION.md`; mutation of request texts confirmed live | P2/P4 adapter targets `apply_guardrail`; transformers only at pre_call/post_call, never during_call |
| Virtual keys / identity context | **adopt** | `UserAPIKeyAuth` (proxy/_types.py:2318) extends the verification-token view: `team_id`, `user_id`, `org_id`, `key_alias`, `team_alias`, `end_user_id`, `metadata`, budgets, `models`. `api_key` is **auto-hashed** by a model validator (`_safe_hash_litellm_api_key`) — hooks never see the raw key | P1 tenant-context contract maps these fields; hashed key = the non-secret `virtual_key_id` OBJECTIVE requires |
| Spend-log content | **adopt** (secure default confirmed) | Prompts/responses stored **only** when `general_settings.store_prompts_in_spend_logs: true` or env `STORE_PROMPTS_IN_SPEND_LOGS` (spend_tracking_utils.py:879-895; default returns `"{}"`). `litellm.turn_off_message_logging` additionally redacts callback payloads; a sanitizer truncates long strings before DB | Keep both flags off in shipped configs; add a config-lint check in P5 `config validate` |
| Streaming guardrails (`async_post_call_streaming_iterator_hook`) | **wrap attachment / build semantics** | Unified impl (unified_guardrail.py:259-410): default `sampling_rate=5` (guardrail runs every 5th chunk over accumulated text), `end_of_stream_only` option, and chunks are **yielded to the client before/without inspection**; its own comment: *"Response already started (we already yielded chunks); cannot send 400"* | Confirms D-005 hard: native streaming mode is detect-after-partial-delivery. `buffer_then_release` must be **built** as our own iterator (yield nothing until scan passes). P12 |
| `during_call` moderation hook | **reject** for transformers; optional for advisory classifiers | Runs parallel via `asyncio.gather`; return values discarded; cannot mutate (proxy/utils.py:1404-1473) | Only exception-based advisory blocking; never dehydration |
| Presidio PII guardrail | **adopt** (optional backend, D-011) | `guardrail_hooks/presidio.py`: `presidio_analyzer_api_base`, `presidio_anonymizer_api_base`, `output_parse_pii`, `pii_entities_config: Dict[PiiEntityType, PiiAction]` (per-entity actions) | P4 `p4.presidio-backend`; entity→action mapping surfaces through InferenceGate policy; masking irreversible (no second rehydration path) |
| Per-guardrail Prometheus metrics | **adopt** | `_record_guardrail_metrics` (latency, status, error_type) fires automatically around every guardrail execution (proxy/utils.py:1050-1060) | Free baseline telemetry for the P4 registry; our safe DTO adds policy/config IDs on top |
| Guardrail load balancing | **wrap** (evaluate in P4) | `_should_use_guardrail_load_balancing` → router `get_available_guardrail` (proxy/utils.py:915-958) | Candidate transport for multiple customer guard endpoints behind one logical control; registry owns semantics/capability gating |
| Guardrail pipelines | **defer** | `_maybe_execute_pipelines` + `_pipeline_managed_guardrails` metadata exist at pre_call | Possible deployment adapter; canonical policy stays InferenceGate control profiles. Re-examine in P5 |
| Model access groups | **adopt** | `model_access_groups: Dict[str, List[str]]` resolution in proxy/auth/model_checks.py:45 | P11 model-class policy (`local-only`, `approved-us-cloud`, …); InferenceGate constrains allowed groups, LiteLLM picks the provider |
| Teams / orgs / budgets / TPM-RPM | **adopt, defer wiring** (D-010) | Fields present throughout `_types.py` (team/org budgets, per-model rpm/tpm limits on keys) | P11. Nothing in P1–P5 may depend on them |
| Custom auth hook | **defer** (D-010) | `user_custom_auth` global + config path exist (proxy_server.py:672-679) | P11 OIDC control-plane flow; known upstream caveats re budget/model-access enforcement under custom auth — verify when P11 opens |
| CORS | **build at ingress** | `origins=["*"]` hardcoded, `allow_credentials=True`, no knob (proxy_server.py:1076, ~1400) | Documented in OPERATIONS.md; revisit on version bump |
| Native TLS | **adopt** (optional) | `--ssl_certfile_path` / `--ssl_keyfile_path` (proxy_cli.py:157-180) | OPERATIONS.md; ingress termination preferred |
| Caching | **defer, default off** | No cache configured in our config.yaml; repo never enables it | Before any enablement: tenant + policy-version in cache key, dehydrated-content-only invariant (OBJECTIVE) |
| Telltale rule engine, control profiles, decision engine, dehydration/rehydration, correlation, session risk | **build** | No native equivalent (guardrail configs are static per-request selections; no policy precedence, simulation, findings model, or manifest store) | The core InferenceGate product: P1–P10 |

## Version policy hooks

- Every "verified" claim above is 1.82.0-specific; the dispatch condition
  `"apply_guardrail" in type(callback).__dict__` and the unified-guardrail
  internals are private implementation details that can shift in patch
  releases. **Any litellm version bump must re-run the integration suite
  (`pytest -m integration`) and re-check this matrix's streaming and
  dispatch rows** — that procedure, plus digest pinning and signature
  verification, belongs to `LITELLM_VERSION_POLICY.md` (P12; deferred per
  D-010).

## Consequences fed into other tasks

1. **P1 contracts:** tenant context maps from `UserAPIKeyAuth`
   (`team_id`→tenant, `org_id`→organization, hashed key→virtual_key_id,
   `end_user_id`→subject); trusted-context resolution happens in our
   adapter, before any control.
2. **P4 registry:** reuse guardrail load balancing + Prometheus metrics;
   gate features per provider capability (D-008).
3. **P5 `config validate`:** assert `store_prompts_in_spend_logs` and
   message logging remain off unless a tenant explicitly opted in.
4. **P12 streaming:** implement `buffer_then_release` ourselves on the
   iterator hook; never enable the native sampled mode for enforcement
   (partial delivery is unavoidable there).
