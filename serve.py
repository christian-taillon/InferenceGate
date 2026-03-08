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
BG_CYAN = "\033[46m\033[30m"
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
        return "127.0.0.1"

def print_instructions(ip, port):
    print("\n" + "═"*60)
    print(f"{BOLD}{GREEN}      🛡️  LITELLM FIREWALL PROXY IS ONLINE{RESET}")
    print("═"*60)
    
    print(f"\n{BOLD}CONNECTION SETTINGS:{RESET}")
    print(f"  {CYAN}Base URL:{RESET}  {BOLD}http://{ip}:{port}/v1{RESET}")
    print(f"  {CYAN}API Key:{RESET}   {BOLD}sk-litellm-firewall-v1-demo{RESET}")
    print(f"  {CYAN}Model:{RESET}     {BOLD}firewall-model{RESET}")

    print(f"\n{BOLD}INTEGRATION GUIDES:{RESET}")
    print(f"  {BOLD}• Same Machine:{RESET}  {CYAN}http://localhost:{port}/v1{RESET}")
    print(f"  {BOLD}• Docker/WSL:{RESET}    {CYAN}http://host.docker.internal:{port}/v1{RESET}")
    print(f"  {BOLD}• Network/LAN:{RESET}   {CYAN}http://{ip}:{port}/v1{RESET}")
    
    print("\n" + "─"*60)
    print(f"{DIM}Logs will stream below. Press {RESET}{BOLD}Ctrl+C{RESET}{DIM} to terminate safely.{RESET}")
    print("─"*60 + "\n")

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
        print_instructions(ip, port)
        process = subprocess.Popen(cmd, env=env)
        process.wait()
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping LiteLLM Firewall...{RESET}")
    except Exception as e:
        print(f"\n{BOLD}Error: {e}{RESET}")

if __name__ == "__main__":
    run_service()
