# LiteLLM Firewall Demonstration

A minimal, production-ready LLM firewall demonstration built using LiteLLM Proxy.

## Purpose
This project provides a reference implementation for a secure AI gateway. It demonstrates how to intercept, assess, and filter LLM requests using both **deterministic regex/keyword rules** and **probabilistic model-based assessment** (Llama Guard).

## Architecture
```text
[ User / App ] 
      |
      v
[ LiteLLM Firewall Proxy ] <--- [ config.yaml ]
      |      |
      |      +-- Phase 1: Built-in Filters (Regex/Keywords)
      |      +-- Phase 2: Llama-Guard-3 Content Assessment
      v
[ Backend AI Model ] (e.g., Qwen, GPT-4, etc.)
```

## Features

### Phase 1: Built-in Content Filters (Regex & Keywords)
Zero-latency, on-device guardrails:
- **PII Blocking**: Automatically prevents leakage of sensitive data (e.g., restricted emails).
- **Prompt Injection Protection**: Blocks common "jailbreak" and instruction-override attempts.
- **Brand Protection**: Enforces corporate safety by blocking competitor mentions.

### Phase 2: Llama-Guard-3 Content Assessment
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

## Running the Demonstration
Run the automated test suite to see the firewall in action:
```bash
uv run demo.py
```

## Customization
Modify `config.yaml` to add your own restricted keywords or adjust the safety thresholds. The logic is fully decoupled from the application code, allowing for security updates without re-deploying your main service.

## License
MIT License. See [LICENSE](LICENSE) for details.
