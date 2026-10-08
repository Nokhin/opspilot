# Local and VPS deployment

One FastAPI/Uvicorn process, static UI, immutable vector snapshot and SQLite.
No GPU or separate database service. Design resource budget: 2 vCPU / 8 GB; Compose app
limits: 1.5 CPU / 2 GiB, one worker, two concurrent investigations.

## Local Docker

```bash
docker compose up --build -d --wait
docker compose exec -T opspilot python -m opspilot.cli evaluate --output var/evaluation
docker compose ps
```

Default URL `http://127.0.0.1:8080`. For a different local port, use
`OPSPILOT_PORT=8180 docker compose up -d --wait`, preserving the same value on recreation.
The named volume contains the DB, index and optional evaluation output. Startup
creates missing stores and preserves existing data. Rebuilding the cached index
requires restarting the app. There is no public ingestion/admin endpoint.

UID/GID 10001, read-only root filesystem, data volume, 16 MiB tmpfs, dropped
capabilities and no-new-privileges. Healthcheck uses cheap local readiness, never an LLM.
`/api/health` is liveness; `/api/ready` checks stores/config, not remote provider health.

## VPS sequence

On supported Linux with Docker Engine/Compose installed, copy project source excluding
`.venv`, `.env`, generated data and caches. Build natively for the VPS architecture.

```bash
cp .env.example .env
chmod 600 .env
# Edit provider/model settings on the VPS only if selecting live mode.
docker compose up --build -d --wait
curl --fail http://127.0.0.1:8080/api/ready
docker compose exec -T opspilot python -m opspilot.cli evaluate --output var/evaluation
```

Use a host HTTPS reverse proxy. Example Caddy config (replace with your domain;
no site is actually deployed by this document):

```caddyfile
opspilot.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Expose the proxy only; the app binds to loopback. A public paid-model demo needs
operator-controlled budget and proxy access/rate limits. V1 has no production auth
or multi-tenancy; offline mode is appropriate for an unrestricted synthetic demo.
Neither mode has privileged/write tools.

## Persistence and updates

`restart` and `down` preserve the named volume. Back it up while the app is stopped
before format changes. `down --volumes` intentionally discards synthetic stores/output.
For an explicit demo rebuild, stop the app, run an operator one-off container/CLI
with `bootstrap --reset`, then restart. An embedding fingerprint mismatch fails
readiness; it never silently resets a cloud/local index.

`.env` is ignored by Git/Docker; settings and credentials are not image layers.
JSON logs contain request ID, route, tool outcomes, source IDs and latency, omitting
raw questions/results/keys. Provider and API errors are sanitised.

## Validation boundary

Native ARM64 and emulated AMD64 checks validate CPU-only packaging.
They are not an actual VPS deployment, load test or live-model availability
test. [Final acceptance](FINAL_ACCEPTANCE.md) records evidence and remaining deployment gates.
