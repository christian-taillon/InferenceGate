<!-- AI OPERATIONAL DIRECTIVES - DO NOT REMOVE -->
# AI Operational Directives
To ensure consistency and high-quality engineering, any AI agent working on this project must follow these core principles:
- **Autonomous Execution:** Take full ownership of tasks, resolving ambiguities through proactive research rather than unnecessary interruptions.
- **Strategic Delegation:** Leverage specialized sub-agents (codebase_investigator, generalist) to "compress" complex research and handle repetitive batch operations efficiently.
- **Iterative Lifecycle:** Rigorously apply the "Research -> Strategy -> Implementation -> Empirical Validation" workflow for every task.
- **Zero-Trust Verification:** Always verify changes through live simulation (e.g., `demo.py`) and automated tests. Never assume success without empirical evidence.
- **Minimalist Engineering:** Favor native LiteLLM configurations and established enterprise patterns over custom code to ensure long-term maintainability.
<!-- END OF AI OPERATIONAL DIRECTIVES -->

# InferenceGate Roadmap (PLAN.md)

This document outlines the strategic phases for evolving this demonstration into an enterprise-ready security gateway for Large Language Models.

---

## Phase 1: Establishing a "Default Secure" Policy (Deterministic)
**Objective:** Replace demo-specific keywords with a comprehensive, industry-standard ruleset for PII, security, and compliance.

### Tasks:
1.  **Research Native LiteLLM Presets:** Investigate `litellm_content_filter` presets for GDPR, HIPAA, and PCI-DSS compliance.
2.  **Community Regex Sourcing:** Identify and curate reliable regex patterns from projects like [OWASP LLM Top 10](https://genai.ovwasp.org/) and [Presidio](https://microsoft.github.io/presidio/) for:
    *   **Financial PII:** Credit card numbers (Luhn check compatible), IBANs, SWIFT codes.
    *   **Identity PII:** SSNs (US), National IDs, Passport numbers.
    *   **Secret Detection:** API Keys, JWT tokens, Private Keys.
    *   **Attack Patterns:** SQL Injection, Prompt Injection payloads (e.g., "DAN" style wrappers).
3.  **Implementation:**
    *   Move from `blocked_words` to `custom_regex_config` in `config.yaml`.
    *   Implement a layered rule approach: `Global` (always block) vs `Model-Specific` (context-aware).

---

## Phase 2: Mature Llama-Guard-3 Integration (Probabilistic)
**Objective:** Improve the reliability, latency, and communication clarity of the Llama-Guard assessment layer.

### Tasks:
1.  **Taxonomy Expansion:** Move beyond simple "unsafe" detection to leveraging the full Llama Guard 3 taxonomy (S1-S13) to provide granular blocking reasons (e.g., "Blocked due to PII" vs "Blocked due to Violent Content").
2.  **Performance Optimization:** 
    *   Implement parallel execution for the safety check vs. the main request (where appropriate).
    *   Evaluate local hosting of `llama-guard3:1b` to minimize gateway-to-gateway latency.
3.  **Client Communication (OpenAI Compatibility):**
    *   Ensure error responses perfectly mirror OpenAI's `moderation` or `refusal` formats to support clients like OpenWebUI and IDE coding tools seamlessly.
    *   Include `system_fingerprint` or `headers` indicating which shield triggered the block.

---

## Phase 3: Project Assessment, Validation, and Reporting
**Objective:** Exhaustively test the gateway and prepare a professional report for enterprise stakeholders.

### Tasks:
1.  **Edge Case Testing:** Develop a "Red Team" test suite to verify:
    *   Multi-lingual prompt injection.
    *   Base64 or obfuscated PII leakage.
    *   Performance under high concurrency (load testing the proxy).
2.  **LiteLLM Feature Audit:** Identify underutilized native features that reduce custom code:
    *   **Virtual Keys:** For team-based budget and rate limiting.
    *   **Semantic Caching:** To avoid re-checking identical safe prompts.
    *   **Request/Response Logging:** Integration with enterprise SIEMs (Splunk, Datadog).
3.  **Reporting:** 
    *   Deliver a "Gap Analysis" report comparing current implementation vs. enterprise requirements (High Availability, Auth integration, Observability).
    *   Propose a "Reference Architecture" for deploying this firewall in a multi-tenant cloud environment.

---

## Phase 4: Automated Testing & CI Readiness ✅
**Objective:** Ensure regression safety with automated tests and prepare for CI/CD integration.

### Tasks:
1.  **Unit Test Suite:** ✅ `tests/test_firewall.py` — **39 tests, all passing**
    *   Regex pattern matching (JWT, SQL injection, prompt injection)
    *   Llama Guard taxonomy integrity (S1-S14)
    *   Error parsing logic (`parse_error` from demo.py)
    *   Config.yaml structure validation
2.  **Regex Refinement:** ✅ All false positives resolved
    *   SQL Injection: Context-aware patterns requiring SQL structural syntax (SELECT...FROM, UPDATE...SET, INSERT INTO, etc.) + stacked query + OR/AND tautology detection
    *   Prompt Injection: Requires article (a/an) after "you are now" and "act as" to distinguish attacks from benign text
    *   Zero xfail markers remaining — all 39 tests pass cleanly
3.  **CI/CD Pipeline:** ✅ `.github/workflows/test.yml`
    *   GitHub Actions runs pytest on push/PR to `main`
    *   Test matrix: Python 3.12 and 3.13
    *   Uses `uv` for fast dependency management
    *   Optional ruff lint check (non-blocking)
    *   ✅ Pre-commit hook: `scripts/install-hooks.sh` (ruff + pytest gate)
    *   ✅ Live smoke test: `tests/smoke_test.py --env <envfile>` (provider connectivity)

### Decisions:
- Tests use import shims to run without live LLM backend or LiteLLM proxy
- `pytest>=8.0.0` added as optional dev dependency (`pip install -e ".[dev]"`)
- README.md port reference corrected from 4000 to 8001
- SQL regex uses compound SQL-syntax patterns instead of bare keyword matching
- Prompt injection regex requires role-assignment context (a/an) after "you are now"

---

## Phase 5: Comprehensive Validation Pass ✅
**Objective:** Thorough end-to-end validation of all code, config, tests, docs, and CI pipeline.

### Validation Battery (T1–T10): All PASS
1.  **T1 — Pytest Suite:** ✅ 39/39 tests passing (`3.49s`)
2.  **T2 — Static Analysis (ruff):** ✅ Clean — no warnings or errors
3.  **T3 — Config Validation:** ✅ `config.yaml` parses; all 3 custom regex patterns compile
4.  **T4 — Regex vs TEST_PROMPTS:** ✅ 0 false positives, 0 false negatives across 24 prompts
5.  **T5 — LlamaGuardShield:** ✅ Instantiation, taxonomy (14 entries), empty-input handling, message extraction all verified
6.  **T6 — Syntax Checks:** ✅ `py_compile` clean on `serve.py`, `demo.py`, `firewall_callbacks.py`
7.  **T7 — GitHub Actions:** ✅ Valid YAML, correct action versions, correct commands
8.  **T8 — Code Quality:** ✅ Unused imports removed from `firewall_callbacks.py` and `serve.py`
9.  **T9 — Documentation:** ✅ Stale "Brand Protection" replaced; master key defaults aligned across `serve.py`/`demo.py`
10. **T10 — Final Report:** ✅ No open issues remaining (INFO severity only)

### Fixes Applied:
- `firewall_callbacks.py`: Removed unused imports (`asyncio`, `Dict`, `List`, `Union`); added defensive null-checks on LlamaGuard response parsing
- `serve.py`: Removed unused `time` import
- `demo.py`: Aligned default master key to `sk-inference-gate-v1`; corrected prompt labels `(Regex)` → `(Built-in)` for prebuilt detections (SSN, IBAN, AWS KEY)
- `README.md`: Replaced stale "Brand Protection" with accurate feature descriptions; updated Customization section

### Commit: `429ab97`

---

## Phase 6: Critical Ship-Blockers (Security Hardening)
**Objective:** Fix the critical flaws identified in `GAP_ANALYSIS.md` that block any production deployment. Grouped by code area to minimize context switching.

### Group A — Shield code (`firewall_callbacks.py` + `config.yaml`)
These touch the same shield plumbing; do together.
1. **Response-side scanning** — add `post_call` guardrail(s) to scan model output for exfil/toxic/secret echo (`config.yaml` currently `pre_call` only). **Risk:** data exfiltration via completions.
2. **Expand shield scope** — `_extract_latest_user_content` only reads latest `user` text (`firewall_callbacks.py:39-53`). Scan full message stack incl. `system`/`developer` and non-text content. **Bypass:** injection via system prompt or prior turns.
3. **Configurable fail-mode** — shields fail open silently on any exception (`firewall_callbacks.py:349-352, 471-474`). Make fail-open/closed configurable per guardrail; emit a counter on failure.
4. **Generic client errors** — `BadRequestError` exposes shield labels/categories (`firewall_callbacks.py:341-348`), parsed into user-facing reasons (`demo.py:235-294`). Return generic `request rejected`; keep detail in server logs.

### Group B — Service bootstrap (`serve.py` + `demo.py`)
5. **Mandatory master key** — refuse to start if `LITELLM_MASTER_KEY` is unset or equals the default `sk-inference-gate-v1` (`serve.py:62-68`, `demo.py:445-453`).
6. **Redact secrets from logs** — `serve.py:64-85` prints the master key to stdout; demo runs `--detailed_debug` to `proxy_debug.log` (`demo.py:444-466`). Never log credentials.

### Group C — Transport (deployment-layer, docs/ingress)
7. **TLS termination** — plain HTTP on `:8001` (`serve.py:55,77-80`). Document/require TLS at proxy or ingress; reject plaintext.

### Group D — CI guardrails
8. **Secret-scanning CI step** — add gitleaks/trufflehog to `.github/workflows/test.yml` to prevent future plaintext leaks.

### Validation
- Add tests: response-side block, system/developer message scan, non-text content, fail-open/closed toggle, secret-free error text, mandatory-key abort.
- Run full `pytest` + `ruff`; add a red-team bypass suite.

---

**Philosophy:** Maintain the "Lite" in LiteLLM. Avoid over-engineering; prefer native features over custom code whenever they meet the security bar.
