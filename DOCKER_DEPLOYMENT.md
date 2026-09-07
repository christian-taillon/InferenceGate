# Docker Deployment Guide: InferenceGate

This guide provides instructions for deploying the InferenceGate in a containerized production environment.

## 1. Prerequisites
- Docker & Docker Compose
- A model backend (e.g., OpenAI, Azure, or self-hosted)
- LiteLLM Master Key (`LITELLM_MASTER_KEY`)

## 2. Dockerfile
Create a `Dockerfile` to package the firewall and its custom callbacks.

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install the shields package; keep the deployment on the verified
# LiteLLM version (DECISIONS.md D-002 / D-014)
COPY pyproject.toml README.md LICENSE ./
COPY inference_gate/ inference_gate/
RUN pip install --no-cache-dir . "litellm[proxy]==1.100.0"

# Gateway config + loader shim (LiteLLM loads guardrail classes from
# .py files relative to the config directory)
COPY config.yaml firewall_callbacks.py ./

# Expose LiteLLM Proxy port
EXPOSE 8001

# Start the proxy
CMD ["litellm", "--config", "config.yaml", "--port", "8001"]
```

## 3. Docker Compose
Use `docker-compose.yml` to orchestrate the gateway and a Redis instance for rate limiting and caching.

```yaml
version: '3.8'

services:
  firewall-gateway:
    build: .
    ports:
      - "8001:8001"
    environment:
      # Required: the proxy refuses to start with an unset/default master key
      - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY}
      - MODEL=${MODEL}
      - LITELLM_API_BASE=${LITELLM_API_BASE}
      - LITELLM_API_KEY=${LITELLM_API_KEY}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis
    restart: always

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    restart: always
```

## 4. Deployment Steps
1.  **Configure Environment:** Create a `.env` file with your API keys and base URLs.
2.  **Build and Start:**
    ```bash
    docker-compose up -d --build
    ```
3.  **Verify:**
    ```bash
    curl http://localhost:8001/health/readiness
    ```

## 5. Security Best Practices
- **Network Isolation:** Ensure the firewall is the *only* entry point for your LLM applications.
- **Secret Management:** Use Docker Secrets or Kubernetes Secrets instead of plain `.env` files in production.
- **Monitoring:** Mount a volume to `/var/log/litellm` and forward logs to a SIEM.
- **TLS Termination (Required for production):** Never expose port `8001` directly to the internet over plain HTTP. Terminate TLS at a reverse proxy (nginx, Caddy, Traefik) or a Kubernetes ingress. Example nginx:
  ```nginx
  server {
      listen 443 ssl;
      server_name inference-gate.internal;
      ssl_certificate     /etc/ssl/inference-gate.crt;
      ssl_certificate_key /etc/ssl/inference-gate.key;
      location / {
          proxy_pass http://firewall-gateway:8001;
          proxy_set_header Host $host;
          proxy_set_header X-Forwarded-Proto https;
      }
  }
  ```
  Reject plaintext on port 8001 by not exposing it externally; only the reverse proxy should bind a public interface.
