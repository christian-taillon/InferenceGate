# Operations — Transport Security (TLS & CORS)

Scope of task `p0.tls-cors-docs`. Verified against installed litellm 1.82.0
source, 2026-07-12. Broader HA/observability runbooks land in P12.

## TLS

The proxy listens plain HTTP on `:8001` (`serve.py`). **Production
deployments MUST NOT expose this port directly.** Two supported patterns:

### 1. Ingress termination (recommended)

Terminate TLS at a fronting reverse proxy / ingress; bind the gateway to
loopback or a private network. Example (Caddy — automatic certificates):

```caddyfile
gateway.example.com {
    reverse_proxy 127.0.0.1:8001
}
```

Equivalent nginx: `listen 443 ssl;` + `proxy_pass http://127.0.0.1:8001;`
with `ssl_protocols TLSv1.2 TLSv1.3;`. In Kubernetes, use an Ingress/Gateway
with TLS and a NetworkPolicy restricting pod ingress to the controller.

Requirements regardless of proxy choice:
- The gateway port must be unreachable from untrusted networks (bind
  `127.0.0.1` or firewall it); plaintext ingress from outside the host or
  pod boundary is a deployment error.
- TLS 1.2+ only; HSTS at the ingress for browser-facing deployments.

### 2. Native TLS

LiteLLM supports direct TLS via CLI flags (verified in
`proxy_cli.py`): `--ssl_certfile_path <cert.pem> --ssl_keyfile_path <key.pem>`.
Suitable for single-node deployments without an ingress. Certificate rotation
requires a process restart; prefer pattern 1 where a fleet or cert automation
exists.

## CORS — verified limitation at 1.82.0

`litellm/proxy/proxy_server.py:1076` hardcodes `origins = ["*"]` and installs
`CORSMiddleware(allow_origins=origins, allow_credentials=True,
allow_methods=["*"], allow_headers=["*"])` (line ~1400). **There is no
config.yaml or env knob for CORS origins at this version.**

Impact: any web origin may issue cross-origin requests to the gateway.
Because authentication is bearer-token (never cookie-based), a hostile page
cannot ride ambient credentials — but permissive CORS still removes a
defense layer and must not reach production as-is.

Required mitigation (until InferenceGate owns ingress policy — tracked for
P11/P12): **strip and enforce CORS at the fronting ingress**, e.g. nginx:

```nginx
proxy_hide_header Access-Control-Allow-Origin;
if ($http_origin != "https://app.example.com") { return 403; }  # simplified
add_header Access-Control-Allow-Origin "https://app.example.com" always;
```

or the equivalent explicit-allowlist CORS config in Caddy/Envoy/ingress
annotations. Default posture: deny browser origins entirely unless a browser
client is an actual requirement.

## Health endpoints

`/health/readiness` is used unauthenticated by `demo.py` and the Docker
docs. Expose liveness/readiness only inside the deployment boundary; do not
route them through the public ingress. Full liveness/readiness split and
authentication policy: P12.
