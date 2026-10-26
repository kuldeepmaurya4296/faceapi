# API reference

Base URL: `https://your-host` (locally `http://127.0.0.1:8000`).
Interactive docs: `/docs` · OpenAPI JSON: `/openapi.json`.

## Authentication

| Mode | How to call |
|---|---|
| Commercial (`FACEAPI_AUTH_ENABLED=true`, default) | `X-API-Key: fk_live_…` on every `/v1/*` call |
| Personal (`FACEAPI_AUTH_ENABLED=false`) | no header at all; unlimited `personal` plan |
| Operator endpoints (`/admin/*`) | `X-Admin-Token: …` — *never* a customer key |

`Authorization: Bearer <key>` is accepted as an alternative to `X-API-Key`.

### Response headers

| Header | Meaning |
|---|---|
| `X-Request-ID` | echo of `X-Request-ID` if you sent one, else generated; also in error bodies |
| `X-Processing-Time-Ms` | server-side handling time |
| `X-RateLimit-Limit` / `X-RateLimit-Remaining` | per-minute budget for this key (absent on unlimited plans) |
| `Retry-After` | seconds to wait, on `429` |
| `X-Quota-Limit` / `X-Quota-Used` | monthly allowance, on quota `429` |

### Errors

All failures use one shape:

```json
{
  "error": {
    "code": "no_face_found",
    "message": "No face detected in the uploaded image.",
    "request_id": "29558065944e490a"
  }
}
```

| Status | `code` | When |
|---|---|---|
| 400 | `unknown_plan`, `invalid_expiry` | admin payload problems |
| 401 | `missing_api_key`, `invalid_api_key`, `key_revoked`, `key_expired` | key problems |
| 401 | `invalid_admin_token` | `/admin/*` without a valid token |
| 403 | `plan_feature_locked` | e.g. trial plan using collections |
| 404 | `not_found` | unknown collection, face or key |
| 409 | `conflict` | collection name already exists |
| 422 | `invalid_image`, `no_face_found`, `face_index_out_of_range`, `invalid_metadata`, `validation_error` | bad input |
| 429 | `rate_limited`, `quota_exceeded` | limits hit |
| 500 | `internal_error` | unexpected |
| 503 | `engine_unavailable` | models could not be loaded |

**Upload limits**: multipart, `image` field; JPEG/PNG/WebP/BMP/TIFF/GIF; the
plan sets the byte limit (default 10 MB); images are downscaled to
`FACEAPI_MAX_IMAGE_SIDE` (1600 px) before detection.

**Billing**: authorised `/v1/*` calls are metered — including ones that later
fail validation (a 422 still consumed compute). `/healthz`, `/readyz`,
`/metrics`, `/docs` and `/admin/*` are never billed.

---

## Face endpoints

### `POST /v1/detect`

Multipart: `image` (file).

| Query param | Type | Default | Notes |
|---|---|---|---|
| `include_landmarks` | bool | `true` | 5 points: right eye, left eye, nose, right mouth, left mouth |
| `max_faces` | int | plan cap | capped by the plan (`max_faces_per_image`) |
| `score_threshold` | float | `0.85` | per-call detector confidence override |

```bash
curl -X POST http://127.0.0.1:8000/v1/detect \
  -H "X-API-Key: $KEY" -F "image=@photo.jpg"
```

```json
{
  "image": { "width": 512, "height": 512, "format": "jpeg" },
  "face_count": 1,
  "faces": [
    {
      "index": 0,
      "box": { "x": 208, "y": 183, "width": 146, "height": 207 },
      "box_normalized": { "x": 0.40625, "y": 0.357422, "width": 0.285156, "height": 0.404297 },
      "score": 0.90898,
      "landmarks": [
        { "x": 249.1, "y": 259.5 }, { "x": 311.4, "y": 258.2 },
        { "x": 281.5, "y": 305.9 }, { "x": 252.3, "y": 350.1 }, { "x": 308.7, "y": 348.4 }
      ]
    }
  ],
  "model": { "detector": "face_detection_yunet_2023mar.onnx", "recognizer": "face_recognition_sface_2021dec.onnx" },
  "usage": { "plan": "starter", "processing_ms": 6.63, "month_usage": 1, "faces_detected": 1, "request_id": "94d341e5bef94776" }
}
```

`face_count: 0` with `faces: []` is a **success** — a photo without people is
not an error.

### `POST /v1/embed`

Multipart: `image`. Returns the 128-d embedding for **one** face.

| Query param | Type | Default | Notes |
|---|---|---|---|
| `mode` | `largest` \| `index` | `largest` | which face to embed |
| `face_index` | int | `0` | used when `mode=index` (0 = largest) |
| `max_faces` | int | plan cap | detection cap |
| `include_crop` | bool | `false` | add the aligned 112×112 JPEG as base64 |

```bash
curl -X POST "http://127.0.0.1:8000/v1/embed?include_crop=true" \
  -H "X-API-Key: $KEY" -F "image=@photo.jpg"
```

Returns `{ image, face_count, faces: [{ index, box, score, embedding: [128 floats], dim: 128, aligned_face_base64 }], model, usage }`.

Embeddings are L2-normalised, so cosine similarity is a plain dot product.
Store them yourself if you want zero-upload comparisons later.

### `POST /v1/verify` (1:1)

Multipart: `image1`, `image2`. Optional `threshold` query param.

```bash
curl -X POST http://127.0.0.1:8000/v1/verify \
  -H "X-API-Key: $KEY" \
  -F "image1=@id-card.jpg" -F "image2=@selfie.jpg"
```

```json
{
  "match": true, "similarity": 0.906898, "threshold": 0.363,
  "faces_in_image1": 1, "faces_in_image2": 1,
  "face_index_image1": 0, "face_index_image2": 0,
  "model": { "...": "..." }, "usage": { "...": "..." }
}
```

The largest face in each image is used. If either image has no face → `422 no_face_found`.

### `POST /v1/compare`

JSON body, no image upload — use this when your own database stores embeddings.

```bash
curl -X POST http://127.0.0.1:8000/v1/compare \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"embedding1": [0.01, ...128 values], "embedding2": [0.02, ...128 values], "threshold": 0.45}'
```

```json
{ "match": true, "similarity": 0.906891, "threshold": 0.45, "dim": 128 }
```

### `POST /v1/identify` (1:N)

Multipart: `image`. Query: `collection` (required), `threshold`, `top_k` (≤50).

```bash
curl -X POST "http://127.0.0.1:8000/v1/identify?collection=customers&top_k=3" \
  -H "X-API-Key: $KEY" -F "image=@visitor.jpg"
```

```json
{
  "collection": "customers",
  "match": true,
  "threshold": 0.363,
  "best_match": { "face_id": "e06b08…", "external_id": "CUST-001", "similarity": 0.9069, "metadata": {"dept": "eng"}, "created_at": "2026-10-08T18:34:20+00:00" },
  "candidates": [ { "...": "..." } ],
  "faces_in_probe": 1,
  "gallery_size": 1,
  "model": { "...": "..." },
  "usage": { "...": "..." }
}
```

`match` is `true` only when the best candidate is at or above the threshold;
`candidates` always includes near-misses so you can build your own review UI.

---

## Collections

All collection endpoints require a plan with `collections: true`
(everything except `trial`), and are scoped to the calling API key.

| Method & path | Purpose |
|---|---|
| `POST /v1/collections` | create `{name, description}` — name matches `[A-Za-z0-9_.-]+`, max 64 chars |
| `GET /v1/collections` | list with `face_count` |
| `GET /v1/collections/{name}` | one collection |
| `DELETE /v1/collections/{name}` | delete the collection **and every face in it** |
| `POST /v1/collections/{name}/faces` | enrol: multipart `image`; form `external_id`, `metadata` (JSON object); query `mode`, `face_index` |
| `GET /v1/collections/{name}/faces` | list, `limit` (≤500) / `offset` |
| `DELETE /v1/collections/{name}/faces/{face_id}` | remove one enrolled face |

```bash
curl -X POST http://127.0.0.1:8000/v1/collections \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name": "customers", "description": "loyalty programme"}'

curl -X POST http://127.0.0.1:8000/v1/collections/customers/faces \
  -H "X-API-Key: $KEY" \
  -F "image=@customer.jpg" -F "external_id=CUST-001" -F 'metadata={"tier":"gold"}'
```

`external_id` is **yours** — the API never invents identities, it only tells you
which of *your* records matched.

---

## Account

### `GET /v1/me`

```json
{
  "key": {
    "key_id": "key_8025f1b17ba398ab", "name": "acme-corp", "plan": "starter",
    "authenticated": true, "personal_mode": false,
    "rate_limit_per_minute": 60, "monthly_quota": 25000,
    "collections_enabled": true, "max_faces_per_image": 50, "month_usage": 7
  },
  "usage": { "month": "2026-10", "requests": 7, "faces": 7, "errors": 0,
             "by_endpoint": [ { "endpoint": "/v1/detect", "requests": 3, "faces": 3, "avg_latency_ms": 7.1, "errors": 0 } ],
             "by_day": [ { "day": "2026-10-08", "requests": 7, "faces": 7 } ] }
}
```

Optional `?month=YYYY-MM`.

---

## Operator endpoints (`/admin/*`, admin token)

| Method & path | Purpose |
|---|---|
| `POST /admin/keys` | issue a key: `{name, plan, email?, expires_at?, monthly_quota?, rate_per_minute?, note?}` → **returns the secret once** |
| `GET /admin/keys?include_revoked=false` | list keys with this month's usage |
| `GET /admin/keys/{key_id}` | one key |
| `PATCH /admin/keys/{key_id}` | change `plan`, `name`, `email`, `active`, `monthly_quota`, `rate_per_minute`, `expires_at`, `note` |
| `POST /admin/keys/{key_id}/revoke` | immediate revocation |
| `DELETE /admin/keys/{key_id}` | delete the key (usage history kept for accounting) |
| `GET /admin/usage/{key_id}?month=YYYY-MM` | per-key usage breakdown |
| `GET /admin/stats?days=30` | service-wide traffic summary |
| `GET /admin/invoices?month=YYYY-MM` | per-customer billable summary |

```bash
curl -X POST http://127.0.0.1:8000/admin/keys \
  -H "X-Admin-Token: $ADMIN" -H "Content-Type: application/json" \
  -d '{"name":"acme-corp","plan":"starter","email":"ops@acme.com","monthly_quota":50000}'
```

```json
{
  "key_id": "key_8025f1b17ba398ab",
  "api_key": "fk_live_rsES7bfDldZmr3sjwPiit403LQEB_zkm",
  "name": "acme-corp", "plan": "starter",
  "monthly_quota": 50000, "rate_limit_per_minute": 60,
  "created_at": "2026-10-08T18:33:41+00:00",
  "warning": "Store this key now. It cannot be recovered later."
}
```

Keys are stored as SHA-256 hashes; a lost key is reissued, never recovered.

---

## Meta endpoints

| Endpoint | Auth | Billed | Purpose |
|---|---|---|---|
| `GET /` | no | no | service discovery, models, plan list |
| `GET /healthz` | no | no | liveness |
| `GET /readyz` | no | no | models + database reachable (503 when not) |
| `GET /metrics` | no | no | Prometheus text: `faceapi_requests_total`, `faceapi_request_latency_ms_sum/count`, `faceapi_faces_detected_total`, `faceapi_uptime_seconds` |
| `GET /docs`, `/redoc`, `/openapi.json` | no | no | interactive docs (disable with `FACEAPI_DOCS_ENABLED=false`) |

---

## Choosing a threshold

Cosine similarity from SFace, measured on the bundled test portraits:

| Pair | Similarity |
|---|---|
| Identical image | 1.000 |
| Same person, different photo (rotate/zoom/exposure) | **0.907** |
| Different people | **0.127** |

The gap is wide, so the default `0.363` is a sensible starting point:

| Use case | Suggested threshold | Cost of being wrong |
|---|---|---|
| Unlocking your own app / low-stakes | 0.30–0.36 | more false accepts |
| Customer-facing "is this the same person?" | 0.40–0.50 | more false rejects |
| Anything security-adjacent | 0.55+ **and** a second factor | — |

Always calibrate on **your** data (your cameras, your lighting, your
demographic mix) with a labelled set, then pick the threshold on the ROC curve
for the error rate you can tolerate. Report FMR/FNMR rather than a "99.9%
accuracy" claim.
