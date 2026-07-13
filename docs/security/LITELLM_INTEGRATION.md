# LiteLLM Integration — Verified Hook Dispatch (1.82.0)

Resolves the core of DECISIONS.md D-004. Method: direct source reading of the
**installed** `litellm==1.82.0` package (`.venv/.../litellm/`), 2026-07-12.
A live proxy trace should still confirm this before P1 engine code ships
(task `p05.capability-matrix`), but the dispatch logic below is unambiguous
in source.

## How `mode: pre_call` actually dispatches

For a config-registered `CustomGuardrail` with `mode: "pre_call"`:

```
proxy pre_call_hook                          (proxy/utils.py:1275)
  └─ for each callback that is a CustomGuardrail:
       _process_guardrail_callback            (proxy/utils.py:961)
         ├─ should_run_guardrail(event_type=pre_call)   # mode gate
         └─ _execute_guardrail_hook(hook_type="pre_call") (proxy/utils.py:863)
              ├─ if "apply_guardrail" in type(callback).__dict__:
              │     data["guardrail_to_apply"] = callback
              │     → UnifiedLLMGuardrails.async_pre_call_hook
              │         → endpoint translation (per CallType)
              │             llms/openai/chat/guardrail_translation/handler.py
              │           ├─ _extract_inputs: collects texts from ALL messages
              │           │   (str content + text parts) and tool calls
              │           ├─ callback.apply_guardrail(inputs={"texts":[...]},
              │           │       request_data=data, input_type="request")
              │           └─ _apply_guardrail_responses_to_input_texts:
              │               WRITES RETURNED TEXTS BACK into the messages
              └─ else: → callback.async_pre_call_hook directly
```

### Consequences (load-bearing for the v2 architecture)

1. **`apply_guardrail` is the live path** for all three custom pre_call
   shields (they define it), and **it can mutate the request** — the
   translation handler writes returned texts back into `data["messages"]`
   before provider dispatch. → **Dehydration is viable as a pre_call
   `apply_guardrail` transformer.** This was the open risk in D-004; resolved
   positively.
2. **Our `async_moderation_hook` implementations are dead code at 1.82.0.**
   - In `pre_call` mode they never run (`during_call_hook` gates on
     `should_run_guardrail(during_call)`).
   - Even in `during_call` mode, classes defining `apply_guardrail` are
     routed through `UnifiedLLMGuardrails.async_moderation_hook` → our
     `apply_guardrail`, never our `async_moderation_hook`
     (proxy/utils.py:1449-1464).
   - Kept for now: they are the only callers of `_extract_all_content`
     (the full-stack-scan invariant helper pinned by tests). Remove in P4
     with parity tests. The dispatch condition
     (`"apply_guardrail" in type(callback).__dict__`) is subtle enough that
     removal should follow, not precede, the live trace.
3. **`during_call` (moderation) runs in parallel with the provider call and
   cannot modify input** — results of `asyncio.gather` are discarded;
   only raised exceptions block (proxy/utils.py:1404-1473). Never place a
   transformer there.
4. **post_call:** `ResponseGuardShield` does **not** define
   `apply_guardrail`, so `use_unified=False` and its
   `async_post_call_success_hook` is invoked directly. Non-streaming only.
5. **Streaming support exists in the unified layer:**
   `UnifiedLLMGuardrails.async_post_call_streaming_iterator_hook` +
   `process_output_streaming_response` (chat translation handler:348-453)
   accumulate per-choice text and run `apply_guardrail` over combined
   windows. This is the candidate mechanism for P12 `chunk_guard` /
   `buffer_then_release` — buffering/release semantics must be verified
   live before any streaming-protection claim (D-005 stands).
6. **Guardrail infrastructure reusable for the guard registry (P4):**
   - Per-guardrail Prometheus metrics are recorded automatically
     (`_record_guardrail_metrics`: latency, status, error_type).
   - Guardrail **load balancing** exists
     (`_should_use_guardrail_load_balancing` → router
     `get_available_guardrail`) — candidate transport for multiple
     customer-supplied guard endpoints behind one logical control.
   - Guardrail **pipelines** exist (`_maybe_execute_pipelines`,
     `_pipeline_managed_guardrails` metadata) — evaluate in p05 as a
     possible deployment adapter; canonical policy remains InferenceGate's.

## Hook → v2 stage mapping (initial)

| LiteLLM hook (1.82.0) | Can mutate? | Blocks via | v2 stages served |
|---|---|---|---|
| `async_pre_call_hook` / unified pre_call → `apply_guardrail(input_type="request")` | **yes** (texts written back) | raise | `request.context`, `pre_provider` (transformers + detectors) |
| `async_moderation_hook` (during_call) | no | raise | advisory-only classifiers where latency overlap is wanted |
| `async_post_call_success_hook` / unified post_call → `apply_guardrail(input_type="response")` | response object | raise | `provider.response`, `client.response` (non-streaming) |
| `async_post_call_streaming_iterator_hook` (unified) | chunk stream | raise / withhold | streaming `provider.response` (P12, verify first) |

## Live confirmation (2026-07-12)

`tests/test_integration_proxy.py` (real proxy + stub upstream, Python 3.13,
`uv run pytest -m integration`) confirmed: input guards execute **before**
the provider call; a guard block means the provider is **never called**;
`ResponseGuardShield` executes after the provider call; block errors carry
only the generic message (no S-codes). Note: the local venv had drifted to
Python 3.14, where uvloop cannot import and the proxy cannot start —
`.python-version` now pins 3.13.

## Still to verify live (p05.capability-matrix)

- Exact `texts` batching, tool-call extraction, behavior for multimodal
  parts (hook *order* is now confirmed live; content plumbing is not).
- Whether message roles are all included by `_extract_inputs` (source reads
  as all messages; confirm system/developer inclusion empirically).
- Streaming iterator buffering: what has already reached the client when the
  guardrail rejects mid-stream.
- Spend-log / `StandardLoggingPayload` content at 1.82.0 (what stores prompt
  or response text, and which settings disable it).
- Virtual keys / teams identity propagation into `user_api_key_dict` for the
  tenant context contract.
