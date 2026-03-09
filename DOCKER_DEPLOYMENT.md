# Docker Deployment Guide: InferenceGate

This guide provides instructions for deploying the InferenceGate in a containerized production environment.

## 1. Prerequisites
- Docker & Docker Compose
- A model backend (e.g., OpenAI, Azure, or self-hosted)
- LiteLLM Master Key (`LITELLM_MASTER_KEY`)

## 2. Dockerfile
Create a `Dockerfile` to package the firewall and its custom callbacks.

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy configuration and callbacks
COPY config.yaml .
COPY firewall_callbacks.py .

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
