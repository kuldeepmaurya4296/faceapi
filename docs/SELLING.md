# Selling the Face API

You have a working, portable face-matching service. This document is about
turning it into revenue: positioning, pricing, unit economics, the operational
workflow, and the legal work that decides whether you can sell it at all.

> **Reality check first.** Face *detection* is a solved, free commodity
> (`face_recognition`, InsightFace, MediaPipe, a hundred GitHub repos). Nobody
> pays for bounding boxes. What people pay for is (a) **face matching that
> works**, (b) **their data staying where they are allowed to keep it**, and
> (c) **someone to call when it breaks**. Price the second and the third, not
> the first.

---

## 1. What you are actually selling

| Positioning | Who it wins against | Sales pitch |
|---|---|---|
| **Self-hosted / data-residency face matching** | AWS Rekognition, Azure Face | "Your customers' faces never leave your servers or your country. No per-call cloud bill." |
| **White-label engine for integrators** | dlib/InsightFace DIY projects | "Docker image + API, your logo, your domain. Integrate in a day instead of a month." |
| **Privacy-first matching for EU/India/ME** | US hyperscalers | "GDPR/DPDP-friendly deployment, DPA included, on your VPS or ours." |
| **Cheap bulk matching** | Hyperscaler list prices | "~90 % cheaper per call at volume, no egress games." |

Hyperscaler list prices for face operations have historically been around
**$1 per 1,000 image analyses** (detection, indexing and comparison billed
separately — AWS Rekognition and Azure AI Face are the usual references; check
their current published rates before you quote against them). Your COGS per
1,000 calls is roughly **$0.0003–0.001** (§4). That gap is the whole business —
and also why you must not compete on price alone, because someone else has the
same gap.

**Do not sell** "identity verification", "KYC", "access control" or "liveness"
as such. This service has no anti-spoofing: a printed photo or a phone screen
will register as a face. If a customer needs that, they need liveness — say so
and lose the deal, rather than win it and get sued.

---

## 2. Who buys

**Best fit (self-serve API):**

* Indie/SaaS developers adding "find me in the event photos" or "tag people"
  features, who don't want to integrate a heavyweight cloud SDK.
* Attendance / visitor-management / HRMS vendors in India, MENA, SEA who need
  matching but must keep biometric data on-premise or in-country.
* Event photography and photo-printing businesses (bulk match + delivery).
* Gym, club and campus management software (member photo check-in, *not* secure
  access control).
* Retail loyalty / repeat-customer analytics teams — **only** with signage,
  notice and consent.

**Best fit (white-label/on-prem licence):**

* System integrators shipping attendance or access products to enterprises.
* Government-adjacent vendors who require an on-prem deployment.
* Other API companies who want to resell matching under their own brand.

**Walk away from:**

* Anyone asking for public-space surveillance, "find this person in the city",
  scraping social media to build a face database, or any law-enforcement use
  without legal process. In the EU the AI Act **prohibits** real-time remote
  biometric identification in publicly accessible spaces by law enforcement and
  the untargeted scraping of facial images to build databases, and it treats
  many biometric systems as high-risk with conformity obligations
  ([EU AI Act guide](https://ai-eu-act.eu/blog/eu-ai-act-prohibited-vs-restricted-high-risk-systems/)).
  Refusing this business is cheaper than the alternative.

---

## 3. Three ways to package it

### A. Self-serve API (what the code already does)

Issue keys with `cli.py keys create`, let customers self-serve. Prepaid is
better than postpaid for a solo operator.

```bash
./.venv/bin/python3 cli.py keys create --name "acme" --plan starter --email ops@acme.com
```

### B. White-label / on-prem licence (highest margin, least scaling pain)

Sell the Docker image + API, one deployment per customer:

* One-time licence **$1,500–$15,000** depending on the customer and region, plus
  **18–25 %/yr** maintenance (updates, support, model refreshes).
* Deliver: `docker-compose.yml`, a `.env` template, an admin token, a short
  operator guide (this repo's docs), and a 30-minute install call.
* Your cost: the same €5 VPS at *their* expense. Margin ≈ 100 %.
* Protect it with a licence key/token check, an offline-friendly contract, and
  by keeping the roadmap value (liveness, quality scoring) in updates.

### C. Embedded/OEM or a vertical product

Bundle matching into a product you sell (attendance app, event gallery, alumni
photo search, real-estate lead dedupe). The API becomes an internal service —
`FACEAPI_AUTH_ENABLED=false` is exactly this mode. Usually far more profitable
than reselling raw API calls, because you're selling an outcome, not a component.

---

## 4. Pricing

### Built-in plans (edit `PLANS` in `app/config.py` to match your market)

| Plan | Price/mo | Included requests | Rate limit | Collections |
|---|---|---|---|---|
| `trial` | $0 | 500 (one-time) | 10/min | ✗ |
| `starter` | $19 | 25,000 | 60/min | ✓ |
| `pro` | $79 | 250,000 | 300/min | ✓ |
| `business` | $299 | 2,000,000 | 1,200/min | ✓ |
| `enterprise` | custom | negotiated | custom | ✓ |
| `personal` | $0 | unlimited | unlimited | ✓ (for you or your own product) |

Overage: $0.60 / $0.35 / $0.15 per additional 1,000 requests. The invoice
endpoint computes all of this for you:

```bash
./.venv/bin/python3 cli.py invoices --month 2026-10
curl -H "X-Admin-Token: $ADMIN" http://localhost:8000/admin/invoices?month=2026-10
```

### Unit economics (measured, not guessed)

Detection costs **4–10 ms** on an Apple-silicon laptop and roughly
**25–40 ms** for a 1600 px image on a 2-vCPU VPS. So one core sustains
~25–35 requests/second.

| | Value |
|---|---|
| VPS | €5/month (2 vCPU, 2 GB, 20 TB traffic on Hetzner-class hosts) |
| Capacity at 50 % utilisation | ~1.0–1.5 M requests/day |
| Compute cost per 1,000 requests | ~**$0.0003–0.001** |
| Egress per 1,000 requests (200 KB images) | ~200 MB — **this becomes your real cost** |
| Gross margin at `starter` ($19 / 25,000) | **> 99 %** |

Two honest consequences:

1. **Break-even is one customer per server.** Your bottleneck is not compute —
   it is support, sales and legal.
2. **Bandwidth and image size matter more than CPU.** Tell customers to send
   cropped, compressed images (640–1024 px, quality 80). Add
   `FACEAPI_MAX_IMAGE_SIDE` guidance to your docs, and consider charging per GB
   if someone uploads 12 MP originals in bulk.

### Price-setting rules

* Charge for **decisions**, not detections: `/v1/verify` and `/v1/identify` are
  worth 10× a `/v1/detect`. Weight them differently in your own plans if you
  like — the usage ledger records the endpoint, so you can change the weighting
  later without changing the API.
* **No free tier without a card**, or a tiny one (500 calls, one-time). Abuse of
  free tiers is the #1 way this business bleeds.
* Annual prepay = 2 months free; it funds your server and kills churn.
* Enterprise: quote 3× your instinct, then discount to 2×.

### Ready-to-paste pricing page

> ### Face matching API — self-hosted, privacy-first
> Detect, compare and search faces with one REST call. Runs on your server or ours.
>
> **Starter — $19/mo.** 25,000 requests, 60/min, collections, email support.
> **Pro — $79/mo.** 250,000 requests, 300/min, priority support, 99.5 % uptime target.
> **Business — $299/mo.** 2M requests, 1,200/min, SLA, invoice billing.
> **On-prem licence — from $1,500.** Docker image, your data never leaves your network, 1 year of updates.
>
> Every plan includes: face detection with landmarks · 128-d embeddings ·
> 1:1 verify · 1:N identify · your own galleries · usage dashboard.
> Overage from $0.15 per 1,000 requests. Cancel any time.
>
> *Not for surveillance, law-enforcement identification, or as the sole factor in
> access control or identity verification.* See our Acceptable Use Policy.

---

## 5. Running the business with this codebase

### Onboarding flow

1. Customer signs up on your landing page → your webhook calls the admin API:

```python
import httpx

def provision_key(customer_name: str, email: str, plan: str = "starter") -> str:
    response = httpx.post(
        "https://api.yourdomain.com/admin/keys",
        headers={"X-Admin-Token": ADMIN_TOKEN},
        json={"name": customer_name, "email": email, "plan": plan},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["api_key"]     # show once, then discard
```

2. Email the key + a 10-line quickstart (copy from `README.md` §Quickstart).
3. Their usage appears in `GET /v1/me` for them and `/admin/usage/{key_id}` for you.

### Monthly billing loop

```bash
./.venv/bin/python3 cli.py invoices --month 2026-10      # per-customer totals
./.venv/bin/python3 cli.py usage --days 30               # service-wide traffic
./.venv/bin/python3 cli.py keys list                     # plan + usage + last seen
```

Then: charge the card / send the invoice, top up quotas with
`cli.py keys update <key_id> --quota N`, and downgrade or revoke
non-payers with `--inactive` / `revoke`. Automate with Stripe metered billing
when the count of customers beats the count of minutes you have.

### Support economics

Support is your biggest cost. Deflect it with:

* `/docs` (Swagger) — already on by default
* `examples/python_client.py` and `examples/curl_cheatsheet.sh`
* a "why did it return no match?" section explaining thresholds
* `X-Request-ID` in every response, so a customer can paste one line and you can
  grep your logs

---

## 6. Compliance: the part that can end the business

Face data is **biometric data** — special-category data in most regimes. You are
a processor for your customers, but you still need your own house in order.

**Hard rules that apply to almost every market**

* Get a **DPA** signed with each business customer; publish a privacy notice
  covering the API, logs and backups.
* **Retention**: define it, enforce it. Example cron:

```bash
# keep the usage ledger for 12 months; face collections are the customer's job
./.venv/bin/python3 -c "from app.config import get_settings; from app.storage import Storage; \
from datetime import datetime,timezone,timedelta; s=Storage(get_settings().db_path); \
cutoff=(datetime.now(timezone.utc)-timedelta(days=365)).isoformat(); print('purged', s.purge_usage_before(cutoff))"
```

* **Encrypt and restrict backups** — they contain embeddings of real people.
* **Never** log or store raw API keys (this service stores only SHA-256 hashes
  and shows a key once).
* Honour deletion requests: deleting a collection/face really deletes the
  embedding; tell customers to do it themselves via the API.

**Regime-by-regime, briefly (verify with a lawyer for your target market)**

| Regime | What it means for you |
|---|---|
| **GDPR (EU/UK)** | Face templates used to identify people are Art. 9 special-category data → explicit consent or another Art. 9(2) basis, DPIA, transparency, retention limits, data-subject rights. Automated decisions need Art. 22 care. |
| **EU AI Act** | Prohibits real-time remote biometric identification in public spaces by law enforcement and untargeted face-image scraping; treats many biometric systems as high-risk with conformity/registration duties. Stay out of public-space surveillance. |
| **Illinois BIPA (US)** | Private right of action, statutory damages ($1,000 negligent / $5,000 reckless). A 2024 amendment limits recovery to **one violation per person** rather than per scan, which cuts class-action exposure dramatically — but written consent and a published retention/destruction policy are still mandatory for Illinois users. |
| **Texas CUBI / Washington HB 1493 / Colorado** | Notice + consent duties, AG enforcement (CUBI up to $25,000 per violation). |
| **India DPDP Act** | Consent must be free, specific and informed, with clear notice; security and erasure duties; obligations scale with volume ("significant data fiduciary"). Rules have been phasing in — check the current status before promising compliance. |
| **Sector rules** | Schools (children = extra care), healthcare, employment screening, finance: expect additional consent, DPIA and audit duties. |

**Your Acceptable Use Policy** — put this on the pricing page and in the terms;
it is what lets you terminate a bad customer instead of being their accomplice:

> You may not use this service for: real-time or bulk surveillance of public or
> private spaces; identifying people without their knowledge; building face
> databases from scraped or third-party images; law-enforcement or intelligence
> identification without lawful process; tracking minors; stalking, harassment
> or discrimination; immigration, employment, housing, credit or insurance
> eligibility decisions; or as the sole factor in identity verification or
> physical access control. You must obtain all notices and consents required by
> law from the people whose faces you submit, and you must not submit images you
> do not have the right to process. Violations lead to immediate termination and
> may be reported.

Then actually enforce it: monitor for sudden bulk enrolment, ask questions, and
keep the right to revoke a key without refund.

---

## 7. Where to find the first ten customers

1. **Your own network, first.** Local attendance/HRMS vendors, event
   photographers, gym software shops. One paid pilot beats a hundred page views.
2. **API directories** (RapidAPI and similar) for passive discovery — treat it
   as lead-gen, not a business.
3. **Integrators, not end users.** One integrator brings ten deployments. Offer
   a white-label licence and a 20 % referral fee.
4. **Content SEO** on the questions your buyers type: "self-hosted face
   recognition API", "AWS Rekognition alternative on-premise", "face matching
   API India data residency", "how much does face recognition cost per 1000
   images". Each maps to one page with real numbers from §4.
5. **Automation ecosystems**: ship n8n/Zapier/Make nodes and a Python/JS SDK.
   Being the "face" node in a no-code flow is durable distribution.
6. **Vertical wedges**: publish a ready-made attendance app or event-photo
   finder built on the API. Products sell services.
7. **Launch**: Product Hunt / Hacker News "Show HN" with the honest angle —
   *"I built a self-hosted Rekognition alternative that runs on a €5 VPS"* —
   plus the real latency and similarity numbers from this repo.

### Cold outreach that works (short, specific, no hype)

> Subject: face matching on your own server (not AWS)
>
> Hi <name> — I saw <product> handles member photos. I run a self-hosted face
> matching API: same box as your app, no per-call cloud fees, faces never leave
> your infrastructure. One curl call to enrol, one to match.
>
> If it's useful I'll give you 5,000 calls free on our server, or a Docker image
> to run yourself in about ten minutes. Want the two-line example?

---

## 8. Common ways this fails

| Failure | Prevention |
|---|---|
| Free-tier abuse (crypto-mining-style bulk calls) | card on file, hard quotas, per-key rate limits, edge limits |
| "Your API said 91 % match, so he's guilty" | put thresholds and error rates in the docs; never call it proof of identity |
| Chargebacks on monthly plans | prepaid credits, annual prepay discount |
| AI Act / BIPA exposure from one customer's use case | Acceptable Use Policy, business verification for high-volume keys, kill switch (`keys revoke`) |
| Zero differentiation, price war to $0 | compete on residency, white-label, support, vertical packaging |
| Support burnout | docs, examples, request IDs, and a plan tier that pays for your time |

Get one paying customer before you optimise anything. The whole stack in this
repo — keys, quotas, usage ledger, invoices — exists so that the boring part of
that first sale takes an afternoon instead of a month.
