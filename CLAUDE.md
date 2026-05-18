# CLAUDE.md

## Project Overview

KONTACT is a **multi-tenant catalog vision RAG agent** — snap photos of product catalogs and contact QRs at trade shows, extract structured data with multi-agent AI vision, and chat with an intelligent agent that runs SQL queries, remembers facts, cites sources with images, and knows who you met.

**Hardened, production-shape**: 25 security/bug fixes/features landed (5 CRITICAL, 8 HIGH, 5 MEDIUM, 4 functional bugs, 3 features) — see "Hardening landmarks" below.

**Architecture**:
```
Phone Camera / Files → Upload (guards) → Queue → Loader (EXIF + QR + phash + blur)
  → Extractor (skip-blurry / Classifier → Specialized agent)
  → URL resolver (for URL QRs)
  → Insert documents + products + contacts + messengers + audit
  → Index ChromaDB + FTS5
  → Chat Agent (SQL tool loop + memory + retry)
```

## Structure

```
City-KONTACT/
├── main.py                     # FastAPI entry (40+ endpoints, SSE, slowapi, CORS env-driven)
├── auth.py                     # bcrypt + passlib + itsdangerous + phonenumbers
├── config.py                   # Env-based config
├── chat.py                     # Agent: RAG + SQL tool loop + memory + OpenRouter retry
├── tools.py                    # SQL tool (UUID-validated TEMP VIEW per user), introspect, summary
├── memory.py                   # Feedback + memories (JSON files)
├── database.py                 # SQLite WAL + FTS5 + 12 tables + audit + FK enforced
├── vectorstore.py              # ChromaDB + prune_orphans + delete_by_folder
├── pipeline/
│   ├── loader.py               # PIL + EXIF + QR + pre-compute blur + phash
│   ├── extractor.py            # Async batch (classifier → agent), skip-blurry, merge loader meta
│   ├── agents.py               # 8 specialized prompts
│   ├── geocode.py              # Nominatim reverse geocode (cached, rate-limited)
│   ├── imagequality.py         # phash + Laplacian blur + near-dup
│   └── url_resolver.py         # NEW: SSRF-safe URL→JSON-LD/OG/regex contact
├── sync/                       # WeChat folder watcher
├── data/
│   ├── kontact.db              # SQLite (WAL + FTS5 + 12 tables)
│   ├── chroma/                 # ChromaDB persistent
│   ├── extractions/            # JSON output files per batch
│   ├── uploads/                # Uploaded batches
│   ├── feedback.json
│   └── memories.json
├── frontend/src/
│   ├── app.css                 # Claude.ai theme (copper/charcoal, Tiempos serif)
│   ├── lib/
│   │   ├── api.ts              # Typed API client (cookie-credentials)
│   │   ├── auth.svelte.ts      # AuthState class w/ $state user/isAdmin
│   │   ├── markdown.ts
│   │   ├── utils.ts            # shortDate/relativeDate helpers
│   │   └── components/         # 13 components: tables, gallery, LocationsMap, Timeline, Tags, Notes, etc.
│   └── routes/
│       ├── +layout.svelte      # Desktop sidebar + mobile bottom nav
│       ├── login/              # email + password only + show-pw + remember
│       ├── upload/             # 3 inputs (camera/library/files) + exifr + geo capture
│       ├── queue/              # Batch list, retry, delete, toast
│       ├── chat/               # Streaming SSE + tool steps + citations + feedback + voice
│       ├── data/               # 20-tab grouped UI: Catalog (7) / Insights (10) / Workspace (3)
│       └── users/              # Admin CRUD
├── Dockerfile                  # Multi-stage (Node + Python + curl healthcheck)
├── docker-compose.yml          # kontact + caddy (profiles:["https"], opt-in)
├── Caddyfile                   # reverse_proxy w/ auto Let's Encrypt
├── deploy.sh
├── requirements.txt            # Pinned (bcrypt 4.0.1 — DO NOT bump to 5.x w/o passlib check)
└── .env.example
```

## Database (12 tables, FK ON, WAL)

```sql
-- Identity + access
users               -- uuid, email, phone_e164 (contact-only), password_hash, pin_hash (unused), role, is_active
login_attempts      -- throttle log (5 fails/15min → 30min lockout)
audit_events        -- upload/login/edit/delete/share/merge

-- Core catalog
documents           -- 50+ cols: products/contact JSON, EXIF, geo, quality, audit
products            -- normalized one-per-row (FK document_id)
contacts            -- normalized + messenger cols (FK document_id)
documents_fts       -- FTS5 virtual

-- Pipeline
queue               -- upload queue w/ owner_uuid + status

-- Chat
chat_history        -- session_id + user_uuid (strict scope)

-- Workspace (aux CRUD)
tags, document_tags, notes, meetings, events
```

### Critical columns on `documents`

| Group | Columns |
|-------|---------|
| Identity | id, uuid, folder, source_file, owner_uuid, is_shared |
| Content | image_type, company, title, products, contact, key_info, raw_text, full_json, metadata |
| EXIF GPS | gps_lat, gps_lng, gps_altitude, gps_heading, gps_speed, gps_source, gps_accuracy |
| Geocode | country, city, address_full |
| Camera | camera_make, camera_model, lens_model, focal_length, f_number, iso, exposure_time, software, sub_sec_time |
| Image | img_width, img_height, file_size_kb, image_phash, blur_score, is_blurry, near_dup_of |
| QR | qr_payloads (JSON), catalog_url |
| Client | client_timezone, client_user_agent, client_ip, client_timestamp, device_signals |
| Audit | created_at, updated_at, edit_count, source_channel |

### Critical columns on `contacts`

```
uuid, document_uuid, document_id, folder, source_file
company, person, phone, phone_e164, email, website, address
whatsapp, wechat_id, wechat_qr_url, viber, telegram, line_id, signal_phone
messengers (JSON), owner_uuid, source_channel
```

## Auth model

**Email + password only.** Login at `/login`; backend `/api/auth/login` rejects non-email identifiers and ignores `pin_hash`.

| Layer | Detail |
|-------|--------|
| Frontend | `<input type="email" autocomplete="email">` — browser validates |
| Backend | `normalize_identifier()` must return `kind="email"`; phone identifier → 401 |
| Password | bcrypt 4.0.1 via passlib; PIN field on user table is unused |
| Session | HttpOnly cookie `kontact_session`, 14-day, itsdangerous-signed |
| Lockout | 5 fails / 15min → 30min cooldown (`is_locked()`) |
| Rate limit | 10/min per-IP via slowapi |
| Legacy | `payload.get('email')` and `payload.get('password')` accepted alongside `{identifier, secret}` |

Phone column (`users.phone_e164`) kept as contact info, not auth. PIN column (`pin_hash`) is dead schema (kept to avoid migration churn).

Super admin bootstrap: `auth.bootstrap_super_admin()` reads `.env` on startup, creates/updates the row.

## Tenancy model

| Role | Sees |
|------|------|
| `super_admin` | everything across all users |
| `admin` | everything (currently equivalent to super_admin) |
| `user` | only rows where `owner_uuid == user.uuid` |

Enforced by:
- `database.visibility_clause(table_alias, user)` — appended to every visible query
- Chat SQL tool — UUID-validated, rewrites `documents/contacts/products` → `user_documents/...` TEMP VIEWs filtered by `owner_uuid`
- Image serve route — joins on `owner_uuid` for non-admin
- `get_chat_history` — strict `user_uuid` filter

## Agent system

### Tool-calling via prompt markers (OpenRouter-compatible)

```
LLM outputs:     [TOOL: query_catalog_db]
                  {"sql": "SELECT company, COUNT(*) FROM products GROUP BY company"}
                  [/TOOL]

Backend parses:  _parse_tool_calls() extracts name + args
Executes:        execute_tool("query_catalog_db", {"sql": "..."}, user=user)
                 ↓ tenancy rewrite → TEMP VIEW per user
Returns:         [RESULT: ...] [/RESULT]
LLM continues:   max 3 tool iterations
```

### Tools

| Tool | Purpose |
|------|---------|
| `query_catalog_db(sql)` | Read-only SQL (SELECT/WITH only, blocked keywords + UUID validate), 50-row cap |
| `introspect_schema(table)` | List tables OR columns/types/samples |
| `get_catalog_summary()` | Stats: docs, products, contacts, companies, GPS count |

### Memory (3 channels)

| Channel | File | Injected as |
|---------|------|-------------|
| Memories | `data/memories.json` | "AGENT MEMORIES" |
| Approved (rating='up') | `data/feedback.json` | "APPROVED RESPONSES" |
| Avoid (rating='down') | `data/feedback.json` | "AVOID THESE PATTERNS" |
| Live | `get_catalog_summary()` | "CATALOG SUMMARY" |

## Pipeline details

### Upload guards (`main.py:upload_images`)

1. Auth check → 401
2. Rate limit (30/min per IP)
3. Per-file MIME allowlist + extension whitelist
4. Safe filename (strip nulls, traversal)
5. Streamed write w/ 100MB cap (raise 413 mid-stream)
6. PDF → 200-page cap, split to JPEGs
7. Queue row created per file w/ `owner_uuid`
8. Background task → `_process_batch`

### Loader (`pipeline/loader.py:load_image`)

1. PIL open + HEIC support
2. `extract_exif` (GPS DMS→decimal, lens/camera/exposure, with unit conversion for altitude/speed)
3. `extract_qr_codes` (pyzbar + cv2 rotation fallback, parsed by type)
4. `compute_blur` Laplacian variance + `is_blurry` flag
5. Resize > MAX_PX (4096), base64 encode for LLM

### Extractor (`pipeline/extractor.py:extract_one`)

1. **If `is_blurry`**: short-circuit → `image_type="blurry"`, no LLM call, returns stub (saves tokens, prevents hallucination)
2. Classifier vision call (Gemini 3.1 Flash Lite, 4000 tokens, temp=0)
3. Specialized agent vision call (8 prompts: product_page, contact_card, qr_card, business_card, price_list, brochure, certification, other)
4. **Merge QR**: vCard overlay, messenger promotion, qr_payloads JSON
5. **Propagate loader meta**: merge `meta` into `data["metadata"]` so EXIF columns get populated downstream

### URL resolver (`pipeline/url_resolver.py:resolve_profile_url`)

Triggered in `_process_batch` for each `qr_type == "url"` payload.

| Stage | Detail |
|-------|--------|
| SSRF guard | block loopback, private, link-local, multicast, `.local`, `.internal` |
| Fetch | httpx 8s timeout, 2MB cap, 4 redirects, browser UA, must be html/xml |
| JSON-LD | Person/Organization/LocalBusiness → name/phone/email/address/jobTitle/sameAs |
| OG meta | og:title→name, og:site_name→company, og:image |
| Links | `mailto:` → email, `tel:` → phone, social hosts → social[] |
| Regex | email + phone fallback on stripped text |
| Normalize | phone → E.164 via phonenumbers (multi-region) |

Merges into `contact` w/o overwriting truthy. Sets `catalog_url` on document.

### Insert (`database.insert_extraction`)

- Single INSERT into documents (NO `INSERT OR REPLACE` — FK collision risk; UNIQUE `file_hash` index dropped)
- Loop products → INSERT (skip dups on error)
- Loop contact fields → `upsert_contact` (separate conn, sees committed doc)
- `_commit()` once at end

## Security

| Layer | Detail |
|-------|--------|
| `SESSION_SECRET` | Startup `RuntimeError` if missing, `<32 chars`, or in placeholder set |
| CORS | `CORS_ORIGINS` env, no `*` w/ credentials |
| Cookie | `httponly`, `samesite=lax`, `secure` env-controlled (`true` in prod) |
| Bcrypt | `bcrypt==4.0.1` pinned — DO NOT bump to 5.x without testing passlib 1.7.5+ |
| SQL injection | UUID strict regex + `uuid.UUID()` parse before TEMP VIEW interpolation |
| Path traversal | `_safe_under()` realpath check; null-byte block |
| Image ownership | doc.owner_uuid join (or super_admin bypass) |
| Upload | MIME allowlist, 100MB cap, safe filename, PIL `MAX_IMAGE_PIXELS=100M` |
| PDF | 200-page cap |
| OpenRouter | 3× exp-backoff retry on 429/5xx/network |
| SSRF | url_resolver IP family block |
| Rate limit | slowapi: 10/min login, 30/min upload, 60/min chat |
| FK enforced | `PRAGMA foreign_keys=ON` on every connection |
| Chroma | daily `prune_orphans` cron + `delete_by_folder` on batch delete |
| Audit | `audit_events` table logs upload/login/edit/delete/share/merge |

## API endpoints

```
# Auth
POST   /api/auth/login          -- 10/min rate limit
POST   /api/auth/logout
GET    /api/auth/me

# Users (admin-only)
GET    /api/users
POST   /api/users               -- create w/ password+pin
PATCH  /api/users/{uuid}
DELETE /api/users/{uuid}

# Upload + queue
POST   /api/upload              -- 30/min, MIME+size+bomb guards, owner_uuid stamped
GET    /api/queue/batches
POST   /api/queue/retry/{id}
DELETE /api/batch/{id}          -- cascades to chroma via delete_by_folder
POST   /api/process/background

# Chat agent
POST   /api/chat                -- 60/min, SQL tool loop
POST   /api/chat/stream         -- SSE: session, tool_call, tool_result, chunk, done
GET    /api/chat/sessions       -- per-user

# Data
GET    /api/data                -- documents (owner-scoped)
GET    /api/documents/{id}
GET    /api/products
GET    /api/contacts
GET    /api/dashboard
GET    /api/search?q=           -- FTS5
GET    /api/search/semantic?q=  -- ChromaDB

# 11 aggregations
GET    /api/aggregations/{locations,countries,timeline,cameras,messengers,
                          qr-codes,quality,duplicates,sync-sources,pricing,map-points}

# Workspace CRUD
{GET POST PATCH DELETE} /api/{tags,notes,meetings,events}

# Image (auth + ownership + realpath)
GET    /api/image/{folder}/{filename:path}

# Export
GET    /api/export/{xlsx,csv,json}

# Other
POST   /api/feedback
GET    /api/memories
GET    /api/config              -- gated
GET    /health                  -- public
```

## Frontend

| Route | Purpose |
|-------|---------|
| `/login` | email + password only, show-pw toggle, remember-me (localStorage base64) |
| `/upload` | hero camera + 3 inputs (camera capture / library / files), exifr@7.1.3, browser geo, sticky upload bar |
| `/queue` | batch rows, inline thumbnails, retry/delete, toast, terminal |
| `/chat` | SSE streaming, RAG ANALYZING animation, tool steps, image citations, thumbs feedback, voice input, export |
| `/data` | 3-section grouped nav (sticky), 20 tabs, hash sync |
| `/users` | admin CRUD |

20 tabs split:
- **Catalog** (7): Documents, Products, Contacts, Companies, Categories, Specs, Gallery
- **Insights** (10): LocationsMap (Leaflet), Timeline, Countries, Messengers, QrCodes, Quality, Duplicates, SyncSources, Cameras, Pricing
- **Workspace** (3): Tags, Notes, Meetings

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI 0.115.6 + Python 3.12 |
| Frontend | SvelteKit 5 + Svelte 5 runes + Tailwind v4 |
| LLM | Gemini 3.1 Flash Lite via OpenRouter |
| Embeddings | OpenAI text-embedding-3-small via OpenRouter |
| DB | SQLite WAL + FTS5 |
| Vectors | ChromaDB |
| Auth | bcrypt 4.0.1 + passlib 1.7.4 + itsdangerous 2.2.0 + phonenumbers 8.13.50 |
| QR | pyzbar 0.1.9 + opencv-python 4.10.0.84 |
| Image | Pillow 11.1.0 + pillow-heif 0.21.0 + imagehash 4.3.1 + PyMuPDF 1.25.3 |
| HTTP | httpx 0.28.1 |
| Parse | beautifulsoup4 4.12.3 |
| Rate limit | slowapi 0.1.9 |
| MIME | python-magic 0.4.27 |
| Deploy | Docker (multi-stage) + Caddy 2-alpine |
| PWA | manifest + service worker (network-first) |

## Configuration (.env)

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `OPENROUTER_API_KEY` | — | YES | LLM |
| `SESSION_SECRET` | — | YES, ≥32 chars | Fails startup if missing/placeholder |
| `SUPER_ADMIN_EMAIL` | — | YES | Bootstrap admin email (used for login) |
| `SUPER_ADMIN_PASSWORD` | — | YES | Bootstrap admin password |
| `SUPER_ADMIN_NAME` | `Super Admin` | | Display name |
| `SESSION_DAYS` | 14 | | Cookie lifetime |
| `COOKIE_SECURE` | auto | | `true` for HTTPS prod |
| `CORS_ORIGINS` | http://localhost:8090 | | Comma-separated; `*` disables credentials |
| `MAX_UPLOAD_BYTES` | 104857600 | | 100MB per file |
| `MAX_IMAGE_PIXELS` | 100000000 | | PIL bomb guard |
| `RATE_LIMIT_ENABLED` | true | | slowapi toggle |
| `DOMAIN` | kontact.example.com | | Caddy TLS |
| `VISION_MODEL` | google/gemini-3.1-flash-lite-preview | | |
| `EMBEDDING_MODEL` | openai/text-embedding-3-small | | |
| `MAX_WORKERS` | 8 | | Extraction concurrency |
| `PORT` | 8000 | | |
| `WECHAT_WATCH_DIR` | — | | Auto-start WeChat watcher |

## Hardening landmarks (this session)

### 🔴 5 CRITICAL (security)
- C1 `SESSION_SECRET` rotated + enforce ≥32 chars at startup
- C2 CORS env-driven; no wildcard with credentials
- C3 UUID strict-validated before TEMP VIEW SQL interpolation (`tools.py`)
- C4 Path traversal: `realpath` + `_safe_under(UPLOADS_DIR)` + null-byte block
- C5 Image ownership: `owner_uuid` join, non-admin can't see others' images

### 🟠 8 HIGH
- H1 Upload size cap (streaming check, 413 on overflow)
- H2 PIL bomb guard (`MAX_IMAGE_PIXELS=100M`)
- H3 MIME allowlist + safe filename sanitizer
- H4 OpenRouter 3× exp-backoff retry on 429/5xx/network
- H5 `PRAGMA foreign_keys=ON` + dropped UNIQUE `file_hash` (FK collision)
- H7 `COOKIE_SECURE` env-driven
- H8 ChromaDB `prune_orphans` daily cron + `delete_by_folder` on batch delete
- (H6 passlib bump deferred — tested, 1.7.4 + bcrypt 4.0.1 stable)

### 🟡 5 MEDIUM
- M1 Specific exception types in pipeline loader (log w/ context)
- M2 slowapi rate limits (10/30/60 per min on login/upload/chat)
- M3 `/api/config` already gated by `current_user`
- M4 PDF page cap 200 + PIL pixel cap covers oversize
- M5 `get_chat_history` strict `user_uuid` (removed `OR IS NULL` leak)

### 🐛 4 functional bugs
- **B1 GPS EXIF**: Extractor wasn't propagating loader meta → `data["metadata"]`. Plus FK collision on file_hash UNIQUE blocked inserts. Now extracted GPS + camera + lens + ISO + geocode all land. Test: B_gps.jpg → gps_lat=31.2304, country=中国, city=上海市.
- **B3 blur hallucination**: F_blur.jpg invented `$8,850` for real `$4,850`. Loader now pre-computes blur; extractor short-circuits on `is_blurry`, marks `image_type="blurry"`, no LLM call, no fake products.
- **Messengers agg empty**: Read flat platform cols (whatsapp/wechat_qr_url/viber/telegram/line_id/signal_phone) in addition to messengers JSON.
- **WhatsApp invite parser**: `wa.me/qr/CODE` was extracting "qr" as phone. Now detects `/qr/<code>` and `/message/<code>` patterns, stores `invite_code`, leaves phone null.

### ✨ 3 features
- **URL profile resolver**: SSRF-safe HTTP fetch + JSON-LD/OG/microdata/regex extraction. URL-type QRs now enrich contacts (test: GitHub QR → "Linus Torvalds" + "GitHub").
- **ChromaDB pruner**: Daily orphan vector cleanup + cascade delete.
- **Email-only login**: simplified auth surface — frontend locked to `type=email`, backend rejects non-email identifiers and ignores PIN. `.env.example` cleaned (no more `SUPER_ADMIN_PHONE`/`SUPER_ADMIN_PIN`).

## Storage backend

`storage.py` — pluggable file storage. Single API: `save_file`, `save_bytes`, `open_stream`, `get_local_path`, `delete`, `delete_prefix`, `exists`, `presigned_url`, `backend_name`.

| `STORAGE_BACKEND` | Behavior |
|-------------------|----------|
| `local` (default) | writes to `data/uploads/` on disk, FastAPI streams via FileResponse |
| `s3` | writes to AWS S3 / R2 / B2 / MinIO / Wasabi; image serve redirects to presigned URL (10-min expiry) |

Upload path: write to local `batch_dir` (always — pipeline needs local file for PIL/QR/EXIF), then `storage.save_file()` mirrors to remote. For local backend this is a no-op (same path).

Migration (`migrate_to_s3.py`): walks existing `data/uploads/` and pushes each file. Idempotent — skips via `head_object`. Run once after switching backend.

Cascading delete: `/api/batch/{id}` removes from SQLite + Chroma + `storage.delete_prefix(batch_id)`.

## Pitfalls / things to know

- **Login is email + password only** — phone/PIN paths removed. `users.pin_hash` still exists in DB but never read by login. Don't re-enable PIN auth without also tightening rate limits (4-digit space is brute-forceable).
- **Bcrypt 4.0.1 PINNED** — passlib 1.7.4 breaks with bcrypt 5.x ("password cannot be longer than 72 bytes")
- **INSERT OR REPLACE deleted** — FK to products/contacts cascades to constraint failure. Use upsert by `(folder, source_file)` only.
- **`file_hash` index** — now plain (not UNIQUE) to avoid REPLACE collision when same image uploaded in different batches
- **Caddy profile opt-in** — `docker compose --profile https up -d` only. Default `docker compose up` = just kontact on 8090.
- **WhatsApp `wa.me/qr/<code>`** — phone NOT extractable without authenticated WA session (ToS-violating). Stores invite deeplink; user resolves via WhatsApp app.
- **Blurry images** — extractor SKIPS LLM call, marks image_type=blurry. Saves tokens + prevents hallucinated specs.
- **TEMP VIEW lifecycle** — created per chat-tool call, dropped via DROP VIEW IF EXISTS. UUID validate is critical (defense in depth).
- **Background EXIF** — server-side `extract_exif()` runs in container; if browser strips EXIF, client-side `exifr@7.1.3` sidecar fills gaps.

## Quick test recipe

```bash
# Smoke test post-changes
docker compose up -d --build kontact && sleep 8

# Login
curl -s -c /tmp/jar -X POST localhost:8090/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin@kontact.local","secret":"<your-pwd>"}' | jq .uuid

# Upload synthetic fixture
curl -s -b /tmp/jar -X POST localhost:8090/api/upload \
  -F "files=@/tmp/kontact_test/B_gps.jpg"

# Wait for processing
for i in {1..10}; do
  curl -s -b /tmp/jar localhost:8090/api/queue/batches | head -c 200
  sleep 5
done

# Verify GPS landed
docker compose exec kontact python3 -c "
import sqlite3; c=sqlite3.connect('/app/data/kontact.db')
for r in c.execute('SELECT folder,source_file,gps_lat,country,city FROM documents ORDER BY id DESC LIMIT 3'):
    print(r)
"
```

## Synthetic fixtures (testing)

In `/tmp/kontact_test/make_fixtures.py`:
- A_catalog.jpg — plain catalog page
- B_gps.jpg — with EXIF GPS (Shanghai 31.2304, 121.4737)
- C_qr_url.jpg — URL QR
- D_qr_vcard.jpg — vCard QR (Zhang Wei, Beijing Tech, +8613912345678)
- E_qr_wechat.jpg — WeChat URL QR
- F_blur.jpg — blurred (should skip extraction)
- G_dup.jpg — near-dup of A
- H_qr_github.jpg — GitHub profile URL (resolver test)

Generate: `/Users/rahulgupta/.venv/bin/python3 /tmp/kontact_test/make_fixtures.py`

## Deploy

```bash
# Dev (HTTP only, port 8090)
docker compose up -d --build kontact

# Prod (HTTPS via Caddy + Let's Encrypt)
# Edit .env: DOMAIN, COOKIE_SECURE=true, CORS_ORIGINS=https://yourdomain
docker compose --profile https up -d

# Healthcheck
curl http://localhost:8090/health
```
