# LiteLLM Firewall

A minimal, non-over-engineered LLM firewall built using LiteLLM Proxy.

## Purpose
This project demonstrates how to set up guardrails and filters for sensitive information (PII) and malicious prompts using LiteLLM's built-in content filters. It acts as a gateway between users and the underlying AI model, ensuring that:
1.  **Sensitive data** (Emails, Credit Cards, Phone Numbers) are **MASKED** before reaching the model.
2.  **Malicious prompts** (Prompt Injection) are **BLOCKED**.
3.  **Competitor brand mentions** are **BLOCKED** (configurable policy).

## Setup
1.  Ensure you have `uv` installed.
2.  Configure your `.env` file with:
    ```env
    baseURL='https://ai.christiant.io/api'
    OPENAI_API_KEY='your-key'
    MODEL='qwen3.5:35b-ctx100k'
    ```
3.  Install dependencies:
    ```bash
    uv sync
    ```

## Running the Demonstration
Execute the demonstration script:
```bash
uv run demo.py
```

The script will:
1.  Start the LiteLLM Proxy in the background using `config.yaml`.
2.  Run a series of tests against the proxy.
3.  Demonstrate real-time masking and blocking.
4.  Cleanly shut down the proxy.

## Configuration
The guardrails are defined in `config.yaml` using `litellm_content_filter`. 

### Guardrails Included:
- **Email Masking**: Uses regex to replace emails with `[EMAIL_REDACTED]`.
- **Phone Number Masking**: Uses regex to replace US phone numbers.
- **Credit Card Masking**: Uses regex to detect common CC formats.
- **Prompt Injection Blocking**: Blocks keywords like "ignore all previous instructions".
- **Competitor Blocking**: Blocks mentions of competitors like "Google", "Microsoft", etc.

## Logs
Detailed logs of the firewall activity can be found in `firewall.log` after running the demo.
