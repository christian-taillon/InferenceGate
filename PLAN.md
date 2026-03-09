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

**Philosophy:** Maintain the "Lite" in LiteLLM. Avoid over-engineering; prefer native features over custom code whenever they meet the security bar.
