import os
import subprocess
import sys
import time
import socket
from dotenv import load_dotenv

# Standard ANSI colors
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

load_dotenv()

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def run_service():
    port = 8001
    
    if is_port_in_use(port):
        print(f"{YELLOW}Warning: Port {port} is already in use.{RESET}")
        print(f"Try running: {BOLD}pkill -f litellm{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{GREEN}      🛡️  INFERENCEGATE PROXY IS ONLINE{RESET}")
    print(f"{DIM}=================================================={RESET}")
    print(f"  {CYAN}Port:{RESET}      {BOLD}{port}{RESET}")
    print(f"  {CYAN}Config:{RESET}    {BOLD}config.yaml{RESET}")
    print(f"  {CYAN}API Key:{RESET}   {BOLD}sk-inference-gate-v1{RESET}")
    print(f"  {CYAN}Model:{RESET}     {BOLD}firewall-model{RESET}")
    print(f"{DIM}=================================================={RESET}\n")

    # Set master key for proxy auth
    env = os.environ.copy()
    env["LITELLM_MASTER_KEY"] = "sk-inference-gate-v1"

    try:
        process = subprocess.Popen(
            [".venv/bin/litellm", "--config", "config.yaml", "--port", str(port)],
            env=env
        )
        process.wait()
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping InferenceGate...{RESET}")
    except Exception as e:
        print(f"\n{BOLD}Error: {e}{RESET}")

if __name__ == "__main__":
    run_service()
