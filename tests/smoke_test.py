"""
Smoke test - verify a live LLM provider is reachable and responds correctly.

Usage:
    .venv/bin/python tests/smoke_test.py               # uses .env (default)
    .venv/bin/python tests/smoke_test.py --env .go.env # uses alternate provider

This script is NOT run by pytest or CI - it requires live credentials.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import dotenv_values
from openai import OpenAI


def default_model() -> str:
    config_path = Path(os.environ.get("LITELLM_CONFIG", "config.yaml"))
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    model = config["model_list"][0]["litellm_params"]["model"]
    return model.removeprefix("openai/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()

    env_path = Path(args.env)
    if not env_path.is_file():
        print(f"FAIL: env file not found: {env_path}")
        return 1

    env = dotenv_values(env_path)
    base_url = env.get("LITELLM_API_BASE") or env.get("baseURL")
    api_key = env.get("LITELLM_API_KEY") or env.get("OPENAI_API_KEY")
    model = env.get("MODEL") or default_model()

    if not base_url or not api_key:
        print(
            "FAIL: env file must define provider base URL and API key using either "
            "LITELLM_API_BASE/LITELLM_API_KEY or baseURL/OPENAI_API_KEY"
        )
        return 1

    host = urlparse(base_url).hostname or "unknown"
    print(f"Provider host: {host}")
    print(f"Model: {model}")

    try:
        client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Respond with exactly: INFERENCE_GATE_OK"}
            ],
            temperature=0,
            max_tokens=300,
        )
        content = response.choices[0].message.content or ""
    except Exception as exc:
        print(f"FAIL: provider request error: {exc}")
        return 1

    print(f"Response: {content}")
    if "INFERENCE_GATE_OK" in content.upper():
        print("PASS")
        return 0

    print("FAIL: response did not contain INFERENCE_GATE_OK")
    return 1


if __name__ == "__main__":
    sys.exit(main())
