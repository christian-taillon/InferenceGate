# InferenceGate Demonstration

A minimal, production-ready LLM Gateway InferenceGate demonstration built using LiteLLM Proxy.

## Purpose
This project provides a reference implementation for a secure AI gateway. It demonstrates how to intercept, assess, and filter LLM requests using **deterministic regex/keyword rules**, **prompt-attack classification** (Llama Prompt Guard 2), and **probabilistic safety assessment** (Llama Guard).

## Architecture
```text
[ User / App ] 
      |
      v
[ InferenceGate Proxy ] <--- [ config.yaml ]
      |      |
      |      +-- Phase 1: Built-in Filters (Regex/Keywords)
      |      +-- Phase 2: Llama-Prompt-Guard-2 Injection Assessment
      |      +-- Phase 3: Llama-Guard-3 Content Assessment
      v
[ Backend AI Model ] (e.g., Qwen, GPT-4, etc.)
```

## Features

### Phase 1: Built-in Content Filters (Regex & Prebuilt Detection)
Zero-latency, on-device guardrails:
- **PII and Secret Blocking**: Automatically prevents leakage of emails, SSNs, IBANs, API keys, JWTs, and similar sensitive values.
- **Prompt Injection Protection**: Blocks common jailbreak and instruction-override attempts.
- **Attack Pattern Detection**: Blocks common SQL injection payloads before they reach the upstream model.

### Phase 2: Llama-Prompt-Guard-2 Prompt Attack Assessment
Focused detection for prompt manipulation attempts:
- **Prompt Injection Detection**: Catches prompts trying to override hidden or developer instructions.
- **Jailbreak Detection**: Blocks known jailbreak-style attempts even when they do not match the static regex rules.

### Phase 3: Llama-Guard-3 Content Assessment
Advanced intent analysis using a specialized safety model:
- **Violent Content Detection**: Detects and blocks prompts about harmful activities (S9).
- **Criminal Intent Detection**: Detects and blocks prompts about theft or illegal acts (S2).

## Setup

1.  **Prerequisites**: Ensure you have [uv](https://github.com/astral-sh/uv) or `pip` installed.
2.  **Environment**: Create a `.env` file based on `.env.example`:
    ```env
    LITELLM_API_BASE='https://your-api-endpoint/v1'
    LITELLM_API_KEY='your-api-key'
    ```
3.  **Install Dependencies**:
    ```bash
    uv sync  # or: pip install -r requirements.txt
    ```

## Running the Service (for Open WebUI)
To run the firewall as a persistent service for Open WebUI or other apps:
```bash
uv run serve.py
```
This will start the proxy on port 8001 and print connection instructions.

## Running the Demonstration
Run the automated test suite to see the firewall in action:
```bash
uv run demo.py
```

Or use the helper script to pick a `.env`, start the demo, or launch the server:
```bash
./scripts/run-demo-stack.sh
./scripts/run-demo-stack.sh serve
```

For an auto-advancing version of the demo, pass a delay in seconds:
```bash
uv run demo.py --delay 2
```

## Customization
Modify `config.yaml` to add your own regex or prebuilt detection rules, or adjust the safety thresholds. The logic is fully decoupled from the application code, allowing for security updates without re-deploying your main service.

## License
MIT License. See [LICENSE](LICENSE) for details.
