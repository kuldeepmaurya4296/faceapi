#!/usr/bin/env bash
#
# Face API — curl cheatsheet. Every call the API supports, copy-paste ready.
#
#   export FACEAPI_URL=http://127.0.0.1:8000
#   export FACEAPI_KEY=fk_live_...        # unset it in personal mode
#   export ADMIN_TOKEN=...                 # for /admin/*
#   bash examples/curl_cheatsheet.sh
#
set -euo pipefail

URL="${FACEAPI_URL:-http://127.0.0.1:8000}"
KEY="${FACEAPI_KEY:-}"
ADMIN="${ADMIN_TOKEN:-}"
IMG1="${IMG1:-tests/assets/person_a_1.jpg}"
IMG2="${IMG2:-tests/assets/person_a_2.jpg}"
IMG3="${IMG3:-tests/assets/person_b_1.jpg}"

# Expand arrays as ${arr[@]+"${arr[@]}"}: an empty array with `set -u` is an
# "unbound variable" error on bash 3.2, which is still /bin/bash on macOS.
auth=()
[ -n "$KEY" ] && auth=(-H "X-API-Key: $KEY")
admin_auth=()
[ -n "$ADMIN" ] && admin_auth=(-H "X-Admin-Token: $ADMIN")

hr() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

hr "service discovery (no auth)"
curl -s "$URL/" | python3 -m json.tool | head -20

hr "liveness / readiness / metrics"
curl -s "$URL/healthz"; echo
curl -s "$URL/readyz"; echo
curl -s "$URL/metrics" | grep -E '^faceapi_uptime_seconds'

hr "1. detect — boxes, landmarks, confidence"
curl -s -X POST "$URL/v1/detect" ${auth[@]+"${auth[@]}"} -F "image=@$IMG1" | python3 -m json.tool

hr "2. detect with a custom confidence threshold, no landmarks, largest 3"
curl -s -X POST "$URL/v1/detect?score_threshold=0.8&max_faces=3&include_landmarks=false" \
  ${auth[@]+"${auth[@]}"} -F "image=@$IMG1" | python3 -m json.tool

hr "3. embed — 128-d vector + aligned crop"
curl -s -X POST "$URL/v1/embed?include_crop=true" ${auth[@]+"${auth[@]}"} -F "image=@$IMG1" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin)["faces"][0]; print("dim",d["dim"],"score",d["score"]); print("embedding[:5]",d["embedding"][:5]); print("crop b64 bytes",len(d["aligned_face_base64"]))'

hr "4. verify 1:1 — same person, two different photos"
curl -s -X POST "$URL/v1/verify" ${auth[@]+"${auth[@]}"} \
  -F "image1=@$IMG1" -F "image2=@$IMG2" | python3 -m json.tool

hr "5. verify 1:1 — different people"
curl -s -X POST "$URL/v1/verify" ${auth[@]+"${auth[@]}"} \
  -F "image1=@$IMG1" -F "image2=@$IMG3" | python3 -m json.tool

hr "6. compare — from embeddings you already stored"
EMB=$(curl -s -X POST "$URL/v1/embed" ${auth[@]+"${auth[@]}"} -F "image=@$IMG1" \
  | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["faces"][0]["embedding"]))')
curl -s -X POST "$URL/v1/compare" ${auth[@]+"${auth[@]}"} -H "Content-Type: application/json" \
  -d "{\"embedding1\": $EMB, \"embedding2\": $EMB}" | python3 -m json.tool

hr "7. collections — create, enrol, list, identify, delete"
curl -s -X POST "$URL/v1/collections" ${auth[@]+"${auth[@]}"} -H "Content-Type: application/json" \
  -d '{"name":"demo","description":"curl cheatsheet"}' | python3 -m json.tool

curl -s -X POST "$URL/v1/collections/demo/faces" ${auth[@]+"${auth[@]}"} \
  -F "image=@$IMG1" -F "external_id=CUST-001" -F 'metadata={"tier":"gold"}' | python3 -m json.tool

curl -s "$URL/v1/collections/demo/faces?limit=10" ${auth[@]+"${auth[@]}"} | python3 -m json.tool

curl -s -X POST "$URL/v1/identify?collection=demo&top_k=3" ${auth[@]+"${auth[@]}"} \
  -F "image=@$IMG2" | python3 -m json.tool

curl -s -X DELETE "$URL/v1/collections/demo" ${auth[@]+"${auth[@]}"}; echo

hr "8. account — plan, quota, usage this month"
curl -s "$URL/v1/me" ${auth[@]+"${auth[@]}"} | python3 -m json.tool

if [ -n "$ADMIN" ]; then
  hr "9. admin — issue a key (secret shown once)"
  curl -s -X POST "$URL/admin/keys" ${admin_auth[@]+"${admin_auth[@]}"} -H "Content-Type: application/json" \
    -d '{"name":"from-curl","plan":"trial"}' | python3 -m json.tool

  hr "10. admin — keys, usage, stats, invoices"
  curl -s "$URL/admin/keys?include_revoked=false" ${admin_auth[@]+"${admin_auth[@]}"} | python3 -m json.tool | head -30
  curl -s "$URL/admin/stats?days=7" ${admin_auth[@]+"${admin_auth[@]}"} | python3 -m json.tool | head -20
  curl -s "$URL/admin/invoices" ${admin_auth[@]+"${admin_auth[@]}"} | python3 -m json.tool | head -30
else
  printf '\n(ADMIN_TOKEN not set — skipping the /admin/* examples)\n'
fi

hr "error shape (401 without a key, when auth is enabled)"
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST "$URL/v1/detect" -F "image=@$IMG1"
curl -s -X POST "$URL/v1/detect" -F "image=@$IMG1" | python3 -m json.tool || true
