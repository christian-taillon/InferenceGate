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
        # Create a dummy connection to detect the preferred local IP
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
    
    print(f"\n{BOLD}Option A: Open WebUI on this SAME machine{RESET}")
    print(f"  API Base URL:  {CYAN}http://localhost:4000/v1{RESET}")
    
    print(f"\n{BOLD}Option B: Open WebUI in DOCKER on this machine{RESET}")
    print(f"  API Base URL:  {CYAN}http://host.docker.internal:4000/v1{RESET}")
    
    print(f"\n{BOLD}Option C: Open WebUI on ANOTHER machine (LAN){RESET}")
    print(f"  API Base URL:  {CYAN}http://{ip}:4000/v1{RESET}")
    
    print(f"\n{BOLD}Common Settings:{RESET}")
    print(f"  API Key:       {CYAN}sk-litellm-firewall-v1-demo{RESET}")
    print(f"  Model Name:    {CYAN}firewall-model{RESET}")
    
    print("\n" + "-"*60)
    print(f"{YELLOW}Ensure your LAN firewall allows traffic on port 4000.{RESET}")
    print("="*60)
    print(f"\n{BOLD}Logs will appear below (Press Ctrl+C to stop)...{RESET}\n")

def run_service():
    port = "4000"
    host = "0.0.0.0" # Bind to all interfaces for LAN access
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # We must ensure LiteLLM itself requires the key we told the user to use
    # We set it as the master key for the proxy
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
        
        # Run the proxy and pipe output directly to terminal
        process = subprocess.Popen(cmd, env=env)
        process.wait()
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping LiteLLM Firewall...{RESET}")
    except Exception as e:
        print(f"\n{BOLD}Error starting service: {e}{RESET}")

if __name__ == "__main__":
    run_service()
