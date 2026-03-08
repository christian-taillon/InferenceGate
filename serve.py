import os
import subprocess
import sys
import time
from dotenv import load_dotenv

# Standard ANSI colors
GREEN = "\033[92m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

load_dotenv()

def print_instructions():
    print("\n" + "="*60)
    print(f"{BOLD}{GREEN}      LITELLM FIREWALL PROXY IS RUNNING{RESET}")
    print("="*60)
    print(f"\n{BOLD}To use this in Open WebUI:{RESET}")
    print(f"\n1. Go to {BOLD}Settings > Connections > OpenAI API{RESET}")
    print(f"2. Set {BOLD}API Base URL{RESET} to:  {CYAN}http://localhost:4000/v1{RESET}")
    print(f"3. Set {BOLD}API Key{RESET} to:       {CYAN}sk-anything{RESET}")
    print(f"4. Click the {BOLD}Refresh{RESET} icon next to the model list.")
    print(f"5. Select {BOLD}firewall-model{RESET} from the dropdown.")
    print(f"\n{BOLD}Note:{RESET} If Open WebUI is in Docker, use {CYAN}http://host.docker.internal:4000/v1{RESET}")
    print("="*60)
    print(f"\n{BOLD}Logs will appear below (Press Ctrl+C to stop)...{RESET}\n")

def run_service():
    port = "4000"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    # We use .venv/bin/litellm to ensure we use the local installation
    cmd = [".venv/bin/litellm", "--config", "config.yaml", "--port", port, "--num_workers", "1"]
    
    try:
        # Give the instructions first
        print_instructions()
        
        # Run the proxy and pipe output directly to terminal
        process = subprocess.Popen(cmd, env=env)
        process.wait()
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping LiteLLM Firewall...{RESET}")
    except Exception as e:
        print(f"\n{BOLD}{RED}Error starting service: {e}{RESET}")

if __name__ == "__main__":
    run_service()
