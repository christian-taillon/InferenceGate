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
RESET = "\033[0m"

load_dotenv()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "0.0.0.0"

def print_instructions(ip):
    print("\n" + "="*60)
    print(f"{BOLD}{GREEN}      LITELLM FIREWALL PROXY IS RUNNING{RESET}")
    print("="*60)
    print(f"\n{BOLD}To use this in Open WebUI (Settings > Connections > OpenAI API):{RESET}")
    print(f"\n{BOLD}Option A: Open WebUI on SAME machine{RESET}  -> {CYAN}http://localhost:4000/v1{RESET}")
    print(f"{BOLD}Option B: Open WebUI in DOCKER{RESET}       -> {CYAN}http://host.docker.internal:4000/v1{RESET}")
    print(f"{BOLD}Option C: Open WebUI on LAN{RESET}          -> {CYAN}http://{ip}:4000/v1{RESET}")
    print(f"\n{BOLD}Settings:{RESET} API Key: {CYAN}sk-litellm-firewall-v1-demo{RESET} | Model: {CYAN}firewall-model{RESET}")
    print("="*60)
    print(f"\n{BOLD}Logs will appear below (Press Ctrl+C to stop)...{RESET}\n")

def run_service():
    port = "4000"
    host = "0.0.0.0"
    env = os.environ.copy()
    
    # CRITICAL: Ensure Python can find firewall_callbacks.py
    env["PYTHONPATH"] = os.getcwd()
    env["PYTHONUNBUFFERED"] = "1"
    env["LITELLM_MASTER_KEY"] = "sk-litellm-firewall-v1-demo"
    
    cmd = [
        ".venv/bin/litellm", 
        "--config", "config.yaml", 
        "--host", host,
        "--port", port, 
        "--num_workers", "1"
    ]
    
    try:
        ip = get_local_ip()
        print_instructions(ip)
        process = subprocess.Popen(cmd, env=env)
        process.wait()
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping LiteLLM Firewall...{RESET}")
    except Exception as e:
        print(f"\n{BOLD}Error: {e}{RESET}")

if __name__ == "__main__":
    run_service()
