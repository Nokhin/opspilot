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

The optional ChatGPT subscription account/model controls are for a native local
server bound to `127.0.0.1`, with one worker and `OPSPILOT_SUBSCRIPTION_ENABLED=true`.
They require loopback clients and same-origin POSTs, so are intentionally unavailable
through container port forwarding or a public reverse proxy. Keep this option disabled
for the Docker/VPS demo. See the [local setup](../README.md#optional-local-chatgpt-subscription-and-model-picker).

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

Earlier V1 native ARM64 and emulated AMD64 checks validate that version's CPU-only packaging.
Fresh V2 image/target-platform validation remains deferred; older container evidence
does not validate the latest V2 source.
They are not an actual VPS deployment, load test or live-model availability
test. [Final acceptance](FINAL_ACCEPTANCE.md) records evidence and remaining deployment gates.

## V2 persistence and offline validation

The same non-root, one-worker container hosts V2. `var/investigations/` is persisted
on the existing data volume and protected by a single-process lock. V2 requests are
serialized within that process. Do not run multiple replicas against one checkpoint
store. Ownership TTL is 24 hours; capacity is 100 investigations, with two retained
checkpoints per completed/interrupted invocation. Expired payloads are purged on the
next store operation. Tokens authorize one synthetic investigation, not production
users or business actions. Source/snapshot changes reject old resumes.

Compose explicitly disables native subscription controls and their default; V1's
configured provider remains selectable through operator configuration. V2 defaults
to offline independently. External LLM usage must be explicitly selected and budgeted.
The image disables external LangSmith tracing; V2 execution also disables tracing
in code. No checkpoint/raw token data belongs in an image or public evidence bundle.

For isolated V2 container evaluation, use a separate data directory or container;
the running API already owns its checkpoint process lock. Example in a fresh
network-disabled container, after building the local image:

```bash
docker run --rm --network none --entrypoint sh opspilot:v2-local -c \
  'python -m opspilot.cli bootstrap && python -m opspilot.cli evaluate-investigations --suite completion --output var/v2-eval'
```

The read-only incident SQLite access is unchanged. Checkpoint writes are confined to
the application-owned data volume, not business records. No actual VPS or HTTPS
rollout is performed by these local instructions.
