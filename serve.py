import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Standard ANSI colors
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

CONFIG_PATH = "config.yaml"

INSECURE_DEFAULT_KEY = "sk-inference-gate-v1"


def load_environment(env_file: str) -> None:
    env_path = Path(env_file)
    if not env_path.is_file():
        raise FileNotFoundError(f"env file not found: {env_path}")

    load_dotenv(env_path, override=True)


def normalize_provider_environment(env: dict[str, str]) -> dict[str, str]:
    normalized = env.copy()

    if not normalized.get("LITELLM_API_BASE") and normalized.get("baseURL"):
        normalized["LITELLM_API_BASE"] = normalized["baseURL"]
    if not normalized.get("LITELLM_API_KEY") and normalized.get("OPENAI_API_KEY"):
        normalized["LITELLM_API_KEY"] = normalized["OPENAI_API_KEY"]
    if not normalized.get("MODEL"):
        normalized["MODEL"] = "openai/qwen3.5:35b-ctx100k"
    elif "/" not in normalized["MODEL"] and normalized.get("LITELLM_API_BASE"):
        normalized["MODEL"] = f"openai/{normalized['MODEL']}"

    return normalized


def refresh_runtime_settings() -> None:
    global CONFIG_PATH
    CONFIG_PATH = os.getenv("LITELLM_CONFIG", "config.yaml")


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def run_service():
    port = 8001

    if is_port_in_use(port):
        print(f"{YELLOW}Warning: Port {port} is already in use.{RESET}")
        print(f"Try running: {BOLD}pkill -f litellm{RESET}")
        sys.exit(1)

    master_key = os.getenv("LITELLM_MASTER_KEY", INSECURE_DEFAULT_KEY)

    if not master_key or master_key == INSECURE_DEFAULT_KEY:
        print(f"{YELLOW}Error: LITELLM_MASTER_KEY is unset or insecure.{RESET}")
        print(
            f"Set a high-entropy key in your .env file, e.g. "
            f"{BOLD}LITELLM_MASTER_KEY='sk-<random-32+>'{RESET}"
        )
        sys.exit(1)

    print(f"\n{BOLD}{GREEN}      🛡️  INFERENCEGATE PROXY IS ONLINE{RESET}")
    print(f"{DIM}=================================================={RESET}")
    print(f"  {CYAN}Port:{RESET}      {BOLD}{port}{RESET}")
    print(f"  {CYAN}Config:{RESET}    {BOLD}{CONFIG_PATH}{RESET}")
    print(f"  {CYAN}API Key:{RESET}   {BOLD}{'*' * 12}{RESET}")
    print(f"  {CYAN}Model:{RESET}     {BOLD}firewall-model{RESET}")
    print(f"{DIM}=================================================={RESET}\n")

    # Set master key for proxy auth
    env = normalize_provider_environment(os.environ.copy())
    env["LITELLM_MASTER_KEY"] = master_key

    try:
        process = subprocess.Popen(
            [".venv/bin/litellm", "--config", CONFIG_PATH, "--port", str(port)],
            env=env,
        )
        process.wait()
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping InferenceGate...{RESET}")
    except Exception as e:
        print(f"\n{BOLD}Error: {e}{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env", help="Environment file to load")
    args = parser.parse_args()

    load_environment(args.env)
    refresh_runtime_settings()
    run_service()
