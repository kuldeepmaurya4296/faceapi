# Deploying the Face API

It is a single CPU-only Python service with one SQLite file. A **€4–5/month VPS
(1–2 vCPU, 1–2 GB RAM, 20 GB disk)** is enough to start selling.

| Resource | Minimum | Comfortable |
|---|---|---|
| CPU | 1 vCPU | 2–4 vCPU |
| RAM | 512 MB | 1–2 GB |
| Disk | 1 GB (image + models) | 20 GB (DB growth + backups) |
| Throughput | ~1.5–3 req/s per vCPU (detect on a 1600 px image) | scales roughly linearly with cores |

---

## Option A — Docker Compose on a VPS (recommended)

### 1. Server prep

```bash
# Ubuntu 24.04, as root
adduser --disabled-password --gecos "" deploy && usermod -aG sudo deploy
apt update && apt upgrade -y
apt install -y ufw git
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

# Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

### 2. Ship the code

```bash
su - deploy
git clone <your-repo> faceapi && cd faceapi     # or: scp -r faceapi deploy@host:~/
cp .env.example .env
```

Edit `.env` — the minimum you must set:

```ini
FACEAPI_ADMIN_TOKEN=<openssl rand -base64 32>
FACEAPI_AUTH_ENABLED=true
FACEAPI_PUBLIC_BASE_URL=https://api.yourdomain.com
WORKERS=2
```

### 3. Start it

```bash
docker compose up -d --build
docker compose logs -f api          # first start prints the admin token + model info
curl -s localhost:8000/healthz
```

Create your first customer key:

```bash
docker compose exec api python cli.py keys create --name "first-customer" --plan starter
```

### 4. HTTPS

```bash
# DNS: an A record for api.yourdomain.com → this server's IP
nano deploy/Caddyfile               # domain + email
docker compose --profile tls up -d
curl -s https://api.yourdomain.com/readyz
```

The `api` service is only published on `${HOST_PORT}`; once Caddy is in front,
bind it to localhost (`HOST_PORT=127.0.0.1:8000:8000`) or drop the `ports:`
entry from `docker-compose.yml` entirely so only Caddy can reach it.

---

## Option B — no Docker (venv + systemd + nginx)

```bash
sudo useradd --system --create-home --home-dir /opt/faceapi faceapi
sudo -u faceapi git clone <your-repo> /opt/faceapi
cd /opt/faceapi
sudo -u faceapi python3 -m venv .venv
sudo -u faceapi ./.venv/bin/pip install -r requirements.txt
sudo -u faceapi ./.venv/bin/python scripts/download_models.py

sudo mkdir -p /var/lib/faceapi /etc/faceapi
sudo chown faceapi:faceapi /var/lib/faceapi
sudo install -m 600 /dev/null /etc/faceapi/faceapi.env
sudo tee /etc/faceapi/faceapi.env >/dev/null <<'EOF'
FACEAPI_AUTH_ENABLED=true
FACEAPI_ADMIN_TOKEN=CHANGE_ME
FACEAPI_DATA_DIR=/var/lib/faceapi
FACEAPI_MODELS_DIR=/opt/faceapi/models
WORKERS=2
EOF

sudo cp deploy/faceapi.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now faceapi
sudo systemctl status faceapi

sudo cp deploy/nginx.conf /etc/nginx/sites-available/faceapi
sudo ln -s /etc/nginx/sites-available/faceapi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.yourdomain.com
```

---

## Option C — managed platforms

Works, with caveats:

* **Google Cloud Run** — deploy the Dockerfile, set `PORT` (the entrypoint honours
  it), `WORKERS=1`, memory ≥ 1 GB, `min-instances=1` to avoid cold starts.
  SQLite **must** live on a mounted volume (Cloud Run volume mounts or Filestore)
  or on GCS-FUSE; otherwise every instance gets its own keys. Simplest correct
  layout: run one instance with a volume, or move storage to Postgres
  (`Storage` is the only class to rewrite).
* **Fly.io** — attach a volume at `/app/data`; `fly deploy` with the Dockerfile.
* **Render / Railway** — Docker deploy + a persistent disk mounted at `/app/data`.
* **AWS ECS/Fargate** — EFS volume for `/app/data`, ALB health check `/readyz`.

Anywhere you get more than one replica **with separate storage**, split-brain is
the risk: issue keys against one instance and the others will not know them.
For multi-replica setups, point `Storage` at Postgres/MySQL or run the key
database on a shared volume (not recommended for SQLite over NFS).

---

## Scaling

| Symptom | Fix |
|---|---|
| CPU saturated, latency rising | more `WORKERS` (≈ vCPU count) or a bigger box; the OpenCV engine is single-threaded per process |
| Need more than one machine | move keys/usage to a shared DB, put instances behind a load balancer |
| Rate limits leak across workers | each process has its own limiter — divide the plan limit by worker count, or add nginx/Cloudflare edge limits (see `deploy/nginx.conf`) |
| Galleries > ~50k faces | replace `Storage.search_faces` with `sqlite-vec`, FAISS or Qdrant (the REST contract stays the same) |
| Images bigger than needed | lower `FACEAPI_MAX_IMAGE_SIDE` to 800–1000; detection cost scales with pixels |

Detection input is set per request to the (downscaled) image size, so throughput
tracks pixel count: a 1600 px image costs ~4× an 800 px image.

---

## Backups

Everything that matters is in one directory:

```bash
# Consistent SQLite backup without stopping the service
docker compose exec api python - <<'PY'
import sqlite3, os
src = sqlite3.connect("/app/data/faceapi.db")
dst = sqlite3.connect("/app/data/backup.db")
src.backup(dst)
print("backup written")
PY
docker compose cp api:/app/data/backup.db ./faceapi-$(date +%F).db
```

Cron example (daily 03:15, keeps 14 days, ships off-box):

```cron
15 3 * * * cd /home/deploy/faceapi && docker compose exec -T api python -c "import sqlite3;sqlite3.connect('/app/data/backup.db').close()" >/dev/null 2>&1; docker compose cp api:/app/data/faceapi.db /backups/faceapi-$(date +\%F).db && find /backups -name 'faceapi-*.db' -mtime +14 -delete
```

Restore: stop the service, replace `data/faceapi.db`, start again. **Losers
beware**: `data/faceapi.db` also contains customer face embeddings — treat
backups as sensitive personal data (encrypt at rest, restrict access, set a
retention period).

---

## Monitoring

```yaml
# prometheus.yml
scrape_configs:
  - job_name: faceapi
    metrics_path: /metrics
    static_configs:
      - targets: ["api.internal:8000"]
```

Alert on:

* `up == 0` or `/readyz` not 200 for 2 minutes
* `rate(faceapi_requests_total{status=~"5.."}[5m]) > 0.05`
* p95 latency: `rate(faceapi_request_latency_ms_sum[5m]) / rate(faceapi_request_latency_ms_count[5m]) > 500`
* a spike in `status="429"` (someone is being throttled — upsell or investigate)
* disk free < 20 % (the SQLite file and its WAL grow with traffic)

Uptime check: `GET /healthz` every minute from outside.

---

## Hardening checklist

- [ ] `FACEAPI_ADMIN_TOKEN` set from a secret manager, not the auto-generated file
- [ ] `FACEAPI_AUTH_ENABLED=true` if anyone else can reach the host
- [ ] `FACEAPI_DOCS_ENABLED=false` in production (or keep `/docs` behind the proxy)
- [ ] `FACEAPI_CORS_ORIGINS` restricted to your own front-ends, not `*`
- [ ] TLS only; HSTS on (Caddy/nginx configs here do it)
- [ ] `/metrics` and `/readyz` not exposed publicly
- [ ] container/user is unprivileged; data dir is a volume with restrictive perms
- [ ] uploads capped (`client_max_body_size` ≥ `FACEAPI_MAX_UPLOAD_MB`)
- [ ] log shipping in place, and **never** log API keys (this service only ever
      prints them once, at creation)
- [ ] automated DB backups + a tested restore
- [ ] retention policy enforced (`storage.purge_usage_before(...)` for the usage
      ledger; delete collections/faces on customer request)
- [ ] a written DPA, privacy notice and consent flow for the people whose faces
      your customers upload
- [ ] incident runbook: how to rotate the admin token, revoke a key, restore a backup

## Updating

```bash
git pull
docker compose up -d --build      # or: systemctl restart faceapi after pip install
```

There are no migrations to run — `Storage` creates missing tables on start. New
columns, if ever added, ship with a small idempotent `ALTER TABLE` in
`storage.py`. Take a backup first if you are jumping many versions.
