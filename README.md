# Face API

**Face detection + face recognition as a self-hosted REST API.** CPU-only, one
SQLite file, ~40 MB of models, no cloud dependency, no per-call licence fees.

Run it privately for your own projects, or put it on a server and sell API keys
to customers — the plan, quota, rate-limit and invoicing machinery is already
built in.

```
POST /v1/detect    → where are the faces? (boxes, landmarks, confidence)
POST /v1/embed     → turn a face into a 128-d vector
POST /v1/verify    → 1:1 — same person?
POST /v1/identify  → 1:N — who is this? (search your own gallery)
POST /v1/compare   → compare two embeddings you already store
```

| | |
|---|---|
| Detection | YuNet 2023 (OpenCV Zoo) |
| Recognition | SFace 2021 (OpenCV Zoo) |
| Runtime | Python 3.10+ · FastAPI · OpenCV (CPU only) |
| Latency | **4–10 ms** per detection on an M-series laptop, ~15–30 ms on a 2-vCPU VPS |
| Storage | SQLite (`data/faceapi.db`) — keys, usage ledger, face galleries |
| Licence of models | Apache-2.0 → resale-friendly |
| Tests | 72 tests, `pytest` in ~1 s |

---

## Quickstart

### 1. Personal mode — no API key, unlimited (30 seconds)

```bash
cd faceapi
bash scripts/setup_local.sh                    # venv + deps + models  (once)

FACEAPI_AUTH_ENABLED=false ./.venv/bin/python3 cli.py serve
```

Open <http://127.0.0.1:8000/docs> for interactive Swagger UI, then:

```bash
curl -X POST http://127.0.0.1:8000/v1/detect -F "image=@photo.jpg"
```

Working clients live in [`examples/`](examples/): `python_client.py` (a small SDK
with a CLI) and `curl_cheatsheet.sh` (every endpoint, copy-paste ready).

No header, no key, no quota. This is the mode to use when the API is a helper
for your own app.

### 2. Commercial mode — issue keys, meter usage (2 minutes)

```bash
./.venv/bin/python3 cli.py serve                       # auth is ON by default

# in another terminal — the admin token is printed at startup, or:
./.venv/bin/python3 cli.py admin-token

./.venv/bin/python3 cli.py keys create --name "acme-corp" --plan starter --email ops@acme.com
#   → API KEY: fk_live_xxxxxxxxxxxxxxxx   (shown once, never stored in plaintext)

curl -X POST http://127.0.0.1:8000/v1/detect \
  -H "X-API-Key: fk_live_xxxxxxxxxxxxxxxx" \
  -F "image=@photo.jpg"
```

### 3. Docker (portable, any VPS)

```bash
cp .env.example .env          # then set FACEAPI_ADMIN_TOKEN (openssl rand -base64 32)
docker compose up -d --build
curl http://localhost:8000/healthz
```

With automatic HTTPS: edit `deploy/Caddyfile` (your domain + email), point the
domain's A record at the server, then `docker compose --profile tls up -d`.

---

## What you get

### Detection & recognition endpoints

* `POST /v1/detect` — face count, bounding boxes (pixel + normalised), 5
  landmarks per face, confidence, sorted largest-first.
* `POST /v1/embed` — L2-normalised 128-d SFace embedding, optionally with the
  aligned 112×112 crop as base64 JPEG.
* `POST /v1/verify` — two images in, `{match, similarity, threshold}` out.
* `POST /v1/compare` — the same decision from embeddings you already have
  (no image upload needed).
* `POST /v1/identify` — 1:N search inside one of your collections, with ranked
  candidates and a threshold decision.

### Collections (per-customer galleries)

`POST /v1/collections`, `POST /v1/collections/{name}/faces` (with your own
`external_id` and arbitrary `metadata`), list, delete. Each API key only ever
sees its own collections.

### Multi-tenancy and money

| Feature | Where |
|---|---|
| API keys, hashed with SHA-256 (plaintext never stored) | `X-API-Key` / `Authorization: Bearer` |
| Plans: trial, starter, pro, business, enterprise, personal | `app/config.py` (`PLANS`) |
| Per-minute rate limiting → `429` + `Retry-After` | `app/security.py` |
| Monthly quota → `429` + `X-Quota-Limit` | `app/storage.py` |
| Usage ledger (endpoint, status, faces, latency, IP) | `usage_events` table |
| Customer self-service: plan + usage | `GET /v1/me` |
| Operator endpoints: issue/update/revoke keys, stats, invoices | `/admin/*` (admin token) |
| Billable summary per customer per month | `GET /admin/invoices`, `cli.py invoices` |

### Ops

* `GET /healthz` (liveness), `GET /readyz` (models + DB), `GET /metrics`
  (Prometheus text format), `/docs` (Swagger), structured logs.
* Every response carries `X-Request-ID` and `X-Processing-Time-Ms`.
* Uniform JSON errors: `{"error": {"code", "message", "request_id"}}`.

---

## Project layout

```
faceapi/
├── app/
│   ├── main.py         FastAPI factory, accounting middleware, routers
│   ├── config.py       settings (FACEAPI_* env vars) + PLANS/pricing
│   ├── engine.py       YuNet detection + SFace recognition (thread-safe)
│   ├── storage.py      SQLite: keys, usage ledger, collections, invoicing
│   ├── security.py     API-key auth, plans, rate limiting, admin token
│   ├── deps.py         shared dependencies + upload handling
│   ├── schemas.py      the public API contract (pydantic)
│   ├── imaging.py      decode/encode, format sniffing, size limits
│   ├── errors.py       typed errors + uniform error envelope
│   ├── metrics.py      Prometheus registry
│   └── routes/         meta, faces, collections, account, admin
├── cli.py              doctor | serve | keys | usage | invoices | stats | models
├── scripts/            download_models.py, setup_local.sh
├── tests/              72 tests (engine, API, commercial, billing)
├── docs/               API.md, DEPLOY.md, SELLING.md
├── examples/           ready-to-run client code
├── Dockerfile · docker-compose.yml · deploy/Caddyfile
└── data/               created at runtime: faceapi.db + admin_token.txt
```

---

## Configuration

Everything is an env var (or `.env`). The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `FACEAPI_AUTH_ENABLED` | `true` | `false` = personal mode, no key required |
| `FACEAPI_ADMIN_TOKEN` | auto-generated | guards `/admin/*` |
| `FACEAPI_VERIFY_THRESHOLD` | `0.363` | cosine threshold for a 1:1 match |
| `FACEAPI_IDENTIFY_THRESHOLD` | `0.363` | cosine threshold for a 1:N match |
| `FACEAPI_DETECT_SCORE_THRESHOLD` | `0.85` | detector confidence floor |
| `FACEAPI_MAX_IMAGE_SIDE` | `1600` | downscale before detection (speed/recall knob) |
| `FACEAPI_DATA_DIR` | `./data` | database + admin token live here |
| `FACEAPI_CORS_ORIGINS` | `*` | lock down for browser clients |

Full list: [.env.example](.env.example) · each plan's limits and prices: `app/config.py`.

---

## Tuning accuracy

* **Default threshold 0.363** is OpenCV's recommendation for SFace cosine
  similarity. Raise it (0.45–0.55) for fewer false accepts; lower it for fewer
  false rejects. The measured gap on the bundled test portraits is wide:
  same person in two different photos ≈ **0.91**, different people ≈ **0.13**.
* **Group photos**: raise `FACEAPI_MAX_IMAGE_SIDE` (e.g. 2400) so small faces
  survive downscaling, and lower `FACEAPI_MIN_FACE_SIZE` if you need tiny faces.
* **Speed**: the detector input is set to the (downscaled) image size per call,
  which is the most accurate configuration. Lower `FACEAPI_MAX_IMAGE_SIDE` to
  800–1000 if you need more throughput.
* **Scale**: inference is CPU-bound and the OpenCV objects are single-threaded,
  so use `--workers` ≈ vCPUs, or run several container replicas.

---

## Testing

```bash
./.venv/bin/python3 -m pytest          # 72 tests, ~1 second
./.venv/bin/python3 cli.py doctor      # environment/model/database check
```

The suite covers detection, embeddings, thresholds, thread safety, image
validation, every endpoint, auth failures, revoked/expired keys, quota and
rate-limit enforcement, plan feature locks, usage metering and invoice maths.

---

## Troubleshooting

**`ImportError: ... different Team IDs` on macOS.**
The base interpreter is signed with the hardened runtime, so it refuses to load
the ad-hoc-signed C extensions that PyPI wheels ship. `scripts/setup_local.sh`
fixes this automatically by re-signing a *copy* of the interpreter inside
`.venv` with `com.apple.security.cs.disable-library-validation`. To do it by hand:

```bash
cp "$(./.venv/bin/python3 -c 'import os,sys;print(os.path.realpath(sys.executable))')" .venv/bin/python3.signed
codesign --force --sign - --entitlements <(printf '%s' '<plist/>') .venv/bin/python3.signed   # see the script for the full plist
```

**`Model file(s) missing`** → `./.venv/bin/python3 scripts/download_models.py`.

**`mkldnn` / `setPreferableTarget` warnings** — harmless OpenCV ARM noise.

---

## Legal & compliance (read before you sell)

Face data is **biometric data**: sensitive personal data under GDPR Art. 9,
regulated by Illinois BIPA, Texas CUBI, India's DPDP Act and similar laws.
Running the software is easy; being allowed to process other people's faces is
a paperwork problem. Concretely:

* Your customers must have a lawful basis and give notice/consent to the people
  whose faces they upload. Put that obligation in your terms, not just in a FAQ.
* Sign a DPA with each business customer; document retention and deletion
  (deleting a collection or face via the API really does delete the embedding).
* This service does **not** do liveness/anti-spoofing detection. Do not market
  it as identity verification, KYC or access control on its own — a printed
  photo can fool it. Say "face matching", not "proves who someone is".
* Accuracy varies by lighting, angle, age, skin tone, glasses and masks. Publish
  your own measured numbers, not the ones from this README.

`docs/SELLING.md` has a fuller go-to-market, pricing and compliance checklist.

---

## Roadmap ideas

Liveness/anti-spoofing, face-quality scoring, quality-gated enrolment,
`sqlite-vec`/FAISS for galleries beyond ~50k faces, Redis-backed global rate
limiting, webhooks on quota thresholds, Stripe metered billing.
# faceapi
