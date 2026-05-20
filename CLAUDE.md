# CLAUDE.md

Internal reference for working on KONTACT. Read this before making changes.

## Project Overview

**Multi-tenant catalog vision RAG agent** — trade-show team uploads catalog photos + business-card QRs, extractors structure the data, agent answers SQL-aware questions about who-met-where.

**Status**: Production-shape. See "Hardening landmarks" + "Session 2 additions" below.

## Session 2 additions (data quality, dedup, admin, guardrails, PWA)

### Data quality
- **Company cascade resolver** (`pipeline/company_resolver.py`): contact.company → doc.company → products[0].company → website-domain → email-domain (generic-provider blocklist). Used at insert (`database.insert_extraction`) + backfill.
- **Backfill jobs** (`pipeline/backfill.py`): `backfill_company()` cheap cascade, `backfill_company_llm()` LLM re-vision (cap 50). Skips `edit_count > 0`. Logs to `events`.
- **Quality score** (`pipeline/extractor.py:_quality_score`): 0-1 confidence × completeness. `documents.quality_score` + `needs_revision` columns. <0.5 flagged.
- **agents.py**: `qr_card` + `contact_page` prompts now include `company` inside `contact` object.

### Dedup + approval
- Tables: `merge_proposals` (keep/drop/reason/confidence/status/before_snapshot/after_snapshot), `merge_blacklist`.
- Scanner (`pipeline/dedup.py`): contacts (phone_e164/email/company+person), documents (file_hash/phash≤4/filename/phash 5-8).
- Engine: reuse `merge_contacts()`; NEW `merge_documents()` (atomic FK reassign products/contacts/tags/notes → keep, delete drop).
- Endpoints: `/api/merge/{scan,proposals,proposals/{id}/approve|reject|swap,proposals/bulk-approve,clusters,clusters/approve,clusters/reject}`.
- UI: `MergeClusters.svelte` — groups duplicates by (keep_uuid, reason), one card per cluster, image thumbs + rich data (products/contact/quality/text snippet), single "merge all" + per-cluster insights.

### Admin (Settings → Admin Insights, super_admin)
- `llm_usage` table + `log_llm_usage()` (wired in extractor + chat). `LLM_PRICING_USD_PER_M` rates.
- Dashboards: `llm_cost_summary()`, `usage_heatmap()`, `conversion_funnel()`, `trade_show_summary()`.
- **Editable cron** (`cron_config` table): `_apply_cron_config()` rebuilds APScheduler live. Endpoints `GET/PATCH /api/admin/jobs/schedule/{id}`.
- **On-demand jobs**: `_JOB_REGISTRY` + `POST /api/admin/jobs/run/{id}` (super_admin). Jobs: vs_prune, backfill_cheap, backfill_llm, dedup_scan, ts_summary.
- Audit Log viewer (`AuditLog.svelte`), `/api/me/stats`.

### Infra
- **SQLite connection pool** (`database.py`): `_PooledConn` subclass, 16 conns (`DB_POOL_SIZE`), WAL + `synchronous=NORMAL` + 20MB cache. Tested 25 concurrent. For ~20 users.
- **Thumbnail endpoint** `/api/thumb/{folder}/{file}?w=256`: PIL resize → disk cache `<folder>/.thumbs/`, 7-day Cache-Control. Grid views use thumbs; lightbox uses full `/api/image`.
- **Filename guard**: upload skips same `(owner, filename)` within 24h unless `force=1`.

### Chat guardrails (`chat.py`)
- Hard pre-filter `_is_injection_attempt()`: regex blocks jailbreak/injection before LLM (ignore-instructions, reveal-prompt, role-change, DAN). `REFUSAL_MESSAGE`.
- System prompt SCOPE section: catalog-data-only, refuse general knowledge/coding/opinions/news/roleplay.
- Applied to `/api/chat` (`ask()`) + `/api/chat/stream`.
- NEW tool `semantic_search_images(query, limit)` (tools.py) → ChromaDB hits w/ `[IMAGE: folder/file]` citations.

### UI restructure
- **Settings** nav (was "More", admin-only) consolidates tabs: Tools / Stats / Users / Admin Insights. Standalone Users nav removed; `UsersManager.svelte` extracted from `/users` route (route still works).
- Regular users see only: Upload / Queue / Agent / Data. Admins also: Sync / Settings.
- Keyboard shortcuts (`/` search, `n` upload, `g`+{d,q,c,u}, `?` help), undo toasts (`undoToast.svelte.ts` + `UndoStack.svelte`), `Skeleton.svelte`, `EmptyState.svelte`, `PullRefresh.svelte`, nav upload badges.

### PWA
- Full icon set (`static/icons/`, 72-512 + maskable + apple-touch + 4 iOS splash). Enriched `manifest.json` (shortcuts, maskable, display_override).
- iOS Safari install-hint banner (no `beforeinstallprompt` on iOS). `app.html` apple meta + splash + theme-color light/dark.
- `sw.js` v3: shell precache, thumb/image cache-first, API network-only w/ offline JSON.

**Architecture**:
```
Phone Camera / Files → Upload (guards + trade_show tag)
  → Queue (per-user owner_uuid)
  → Loader (EXIF + 40+ QR/barcode parsers + phash + blur)
  → Extractor (skip-blurry → classifier → specialized agent → merge QR)
  → URL resolver (JSON-LD/OG/microdata for URL-type QRs)
  → Insert documents + products (+currency/price_amount) + contacts + meetings (from VEVENT) + audit
  → Auto-tag (industry, region, signals)
  → Storage mirror (local or S3)
  → Index ChromaDB + FTS5
  → Chat (SQL tool loop + per-user memory + streaming + 3× retry)
```

## Structure

```
City-KONTACT/
├── main.py                     # FastAPI (50+ endpoints, SSE, slowapi per-user, CORS env)
├── auth.py                     # bcrypt + passlib + itsdangerous + phonenumbers (email-only)
├── storage.py                  # Pluggable LocalStorage / S3Storage (boto3)
├── config.py
├── chat.py                     # Agent: RAG + SQL tool loop + memory + OpenRouter retry
├── tools.py                    # SQL tool (UUID-validated TEMP VIEW per user)
├── memory.py
├── database.py                 # SQLite WAL + FTS5 + 12 tables + FK enforced
├── vectorstore.py              # ChromaDB + prune_orphans + delete_by_folder
├── pipeline/
│   ├── loader.py               # PIL + EXIF + 40+ QR/barcode parsers + blur + phash
│   ├── extractor.py            # Async batch (classifier → agent), skip-blurry, merge loader meta
│   ├── agents.py               # 8 specialized prompts
│   ├── geocode.py              # Nominatim reverse geocode (cached, rate-limited)
│   ├── imagequality.py         # phash + Laplacian blur + near-dup
│   ├── url_resolver.py         # SSRF-safe URL→JSON-LD/OG/regex contact
│   ├── tagger.py               # Heuristic auto-tagger (industry/region/signal)
│   └── pricing.py              # Currency + numeric amount parser
├── sync/                       # WeChat folder watcher
├── data/                       # Runtime: kontact.db, chroma/, uploads/, extractions/, *.json
├── frontend/src/
│   ├── lib/
│   │   ├── uploadQueue.svelte.ts        # Global UploadQueueState singleton
│   │   ├── components/UploadTray.svelte # Floating tray (mounted in +layout)
│   │   ├── components/Gallery.svelte    # Group-by + multi-select + lightbox
│   │   └── components/CategoriesTable.svelte  # Image grids per category + AI button
│   └── routes/
│       ├── profile/+page.svelte         # Change password page
│       └── upload/+page.svelte          # 2-button compact layout
├── backup.sh                   # Full system snapshot → backups/*.tar.gz
├── restore.sh
├── migrate_to_s3.py            # One-shot upload migration
├── Dockerfile / docker-compose.yml / Caddyfile
├── requirements.txt            # bcrypt 4.0.1 PINNED, slowapi, boto3, etc.
└── .env.example
```

## Database (12 tables, FK ON, WAL)

```sql
users               uuid, email, phone_e164 (contact-only), password_hash,
                    pin_hash (unused), role, is_active, last_login
documents           50+ cols: products/contact JSON, EXIF, geo, quality,
                    audit, trade_show
products            normalized + currency + price_amount
contacts            normalized + messenger cols (whatsapp, wechat_qr_url,
                    viber, telegram, line_id, signal_phone)
documents_fts       FTS5 virtual
queue               owner_uuid + trade_show + status
chat_history        session_id + user_uuid (strict scope)
login_attempts      throttle log
audit_events        upload/login/edit/delete/share/merge
tags, document_tags, notes, meetings, events    workspace CRUD
```

## Tenancy model

| Role | Sees |
|------|------|
| `super_admin` | everything across all users |
| `admin` | everything (equivalent to super_admin) |
| `user` | only rows where `owner_uuid == user.uuid` |

Enforced by:
- `database.visibility_clause(table_alias, user)` — appended to every query
- Chat SQL tool — UUID-validated, rewrites `documents/contacts/products` → `user_documents/...` TEMP VIEWs filtered by `owner_uuid`
- Image serve — joins on `owner_uuid` for non-admin
- `get_chat_history` — strict `user_uuid` filter (no `OR IS NULL` legacy)
- `/api/queue/batches` — per-user filter (fixed this session)

## Auth model

**Email + password only.** Phone/PIN paths removed.

| Layer | Detail |
|-------|--------|
| Frontend | `<input type="email" autocomplete="email">` |
| Backend | `normalize_identifier()` must return `kind="email"`; phone identifier → 401 |
| Password | bcrypt 4.0.1 via passlib; PIN column dead schema |
| Session | HttpOnly cookie `kontact_session`, 14-day, itsdangerous-signed |
| Lockout | 5 fails / 15min → 30min cooldown |
| Rate limit | 10/min/IP login; 60/min/user upload; 120/min/user chat (slowapi) |
| Legacy | `{email, password}` accepted alongside `{identifier, secret}` |

Super admin bootstrap: `auth.bootstrap_super_admin()` reads `.env` at startup.

## Agent system

Tool-calling via prompt markers (OpenRouter-compatible — no native tool_use):

```
LLM outputs:     [TOOL: query_catalog_db]
                  {"sql": "SELECT company, COUNT(*) FROM products GROUP BY company"}
                  [/TOOL]

Backend:         _parse_tool_calls() → execute_tool(name, args, user=user)
                 → UUID validate → TEMP VIEW per user → return markdown
LLM sees:        [RESULT: ...] [/RESULT]  →  generates final answer
Max iterations:  3 tool calls per question
```

Tools: `query_catalog_db(sql)`, `introspect_schema(table)`, `get_catalog_summary()`

Memory: `data/memories.json` (manual), `data/feedback.json` (thumb up/down), live `get_catalog_summary()` injected as system context.

## Pipeline details

### Upload (`main.py:upload_images`)
1. Auth + rate limit
2. Per-file MIME allowlist + extension whitelist + safe filename
3. Streamed write with 100MB cap (raise 413 mid-stream)
4. PDF → 200-page cap, split to JPEGs
5. Storage mirror (`storage.save_file` — no-op local, PUT to S3)
6. Queue row with `owner_uuid + trade_show`
7. Background task → `_process_batch`

### Loader (`pipeline/loader.py:load_image`)
1. PIL open + HEIC support
2. `extract_exif`: GPS DMS→decimal, lens/camera/exposure with unit conversion
3. `extract_qr_codes`: pyzbar + cv2 + rotation fallback, dispatch to 13 parsers
4. `compute_blur` + `is_blurry` flag (pre-extractor)
5. Resize > MAX_PX, base64 encode for LLM

### Extractor (`pipeline/extractor.py:extract_one`)
1. **`is_blurry`?** → short-circuit `image_type="blurry"`, no LLM (saves tokens, prevents hallucination)
2. Classifier (Gemini 3.1 Flash Lite, temp=0)
3. Specialized agent vision call (8 prompts)
4. **Merge QR**: vCard/MeCard overlay, messenger promotion, payload JSON
5. **Propagate loader meta**: merge EXIF into `data["metadata"]` so flat columns populate

### URL resolver (`pipeline/url_resolver.py`)
Triggered in `_process_batch` for `qr_type == "url"`.
- SSRF guard (private/loopback/link-local/`.local`)
- httpx 8s timeout, 2MB cap, 4 redirects
- JSON-LD Person/Organization → name/phone/email/address/jobTitle/sameAs
- OG meta → name/company/image
- mailto/tel/social hosts
- Regex fallback + phone E.164 normalization

### Auto-tagging (`pipeline/tagger.py:suggest_tags`)
Heuristic. No extra LLM call. Returns up to 6:
- Content type from `image_type`
- Industry from keyword match
- Region from geocoded country
- Signal flags (has-qr / has-messenger / has-phone / has-email / has-pricing)

### Currency parsing (`pipeline/pricing.py:parse_price`)
Returns `(ISO_4217, float)`:
- Symbol prefix/suffix (`$`, `€`, `¥`, `£`, `₹`, `₩`, `R$`, `HK$`, `C$`, `A$`, `S$`, `NT$`, `Mex$`, `₽`, `฿`, `₫`)
- Word/ISO match (`USD`, `EUR`, `RMB`, `元`, `RUPEE`, `YEN`, …)
- Smart decimal/thousand separator handling (US `1,234.56` vs EU `1.234,56`)

### Insert (`database.insert_extraction`)
- Single INSERT into documents (NO `INSERT OR REPLACE` — FK collision risk)
- Loop products → INSERT with `currency` + `price_amount` (parsed)
- Loop contact fields → `upsert_contact` (separate conn, sees committed doc)
- Single `commit()` at end

## Storage backend (`storage.py`)

Pluggable. API: `save_file`, `save_bytes`, `open_stream`, `get_local_path`, `delete`, `delete_prefix`, `exists`, `presigned_url`, `backend_name`.

| `STORAGE_BACKEND` | Behavior |
|-------------------|----------|
| `local` (default) | writes to `data/uploads/`, FastAPI streams via FileResponse |
| `s3` | writes to AWS S3 / R2 / B2 / MinIO / Wasabi; image serve redirects to presigned URL (10-min) |

Upload path: write to local `batch_dir` (always — pipeline needs PIL/QR/EXIF), then `storage.save_file()` mirrors to remote. Cascading delete on `/api/batch/{id}` removes SQLite + Chroma + storage prefix.

Migration script: `migrate_to_s3.py` walks `data/uploads/` and pushes each file. Idempotent (head_object check).

## Backup + restore

| Script | Purpose |
|--------|---------|
| `backup.sh` | WAL checkpoint → docker cp data → bundle `.env` + manifest → `.tar.gz` |
| `restore.sh` | Stop container → restore .env (keeps pre-restore copy) → overwrite /app/data → restart |

Tested: 2MB archive on dev (18 docs, 8 products, 50 chat msgs). Backups gitignored.

## API endpoints

```
# Auth
POST   /api/auth/login              email + password, 10/min/IP
POST   /api/auth/logout
GET    /api/auth/me

# Users (admin-only)
GET POST PATCH DELETE /api/users{/uuid}

# Upload + queue
POST   /api/upload                  60/min/user, accepts trade_show form field
GET    /api/queue/batches           per-user filtered
GET    /api/queue                   status counts
POST   /api/queue/retry/{id}
DELETE /api/batch/{id}              cascades DB + Chroma + storage

# Chat
POST   /api/chat                    120/min/user, SQL tool loop
POST   /api/chat/stream             SSE
GET    /api/chat/sessions           per-user
GET    /api/chat/history/{sid}
DELETE /api/chat/sessions/{sid}

# Data + filters
GET    /api/data?trade_show=&country=&has_qr=&has_gps=
GET    /api/documents/{id}
GET    /api/products                includes currency + price_amount
GET    /api/contacts
GET    /api/contacts/duplicates     dedup suggestions (phone_e164/email)
POST   /api/contacts/merge          keep_uuid + drop_uuid
POST   /api/auth/change-password    self-service, requires current_password
POST   /api/categories/auto         AI categorize products (batch 12/LLM call)
GET    /api/contacts/{uuid}/vcard   .vcf download
PATCH  /api/contacts/{uuid}
DELETE /api/contacts/{uuid}
GET    /api/export/vcards.zip       bulk
GET    /api/search?q=               FTS5
GET    /api/search/semantic?q=      ChromaDB

# 12 aggregations
GET    /api/aggregations/{locations,countries,timeline,cameras,messengers,
                          qr-codes,quality,duplicates,sync-sources,pricing,
                          map-points,trade-shows}

# Workspace CRUD
{GET POST PATCH DELETE} /api/{tags,notes,meetings,events}

# Image (auth + ownership + realpath; S3 backend redirects to presigned)
GET    /api/image/{folder}/{filename:path}

# Export
GET    /api/export/{xlsx,csv,json}

# Other
POST   /api/feedback
GET    /api/memories
GET    /api/config                  auth-gated
GET    /health                      public
```

## Frontend

| Route | Purpose |
|-------|---------|
| `/login` | email + password only, show-pw toggle, remember-me |
| `/upload` | hero camera + 3 inputs (camera capture / library / files), trade-show input (persisted), exifr@7.1.3 client EXIF, browser geo, auto-submit + auto-redirect |
| `/queue` | batch rows, inline thumbnails → **lightbox** with full image + side panel, retry/delete, toast |
| `/chat` | SSE streaming, RAG ANALYZING animation, tool steps, image citations, thumbs feedback, voice input, export |
| `/data` | 3-section grouped nav (Catalog 7 / Insights 10 / Workspace 3) — 20 tabs total |
| `/users` | admin CRUD |

Layout-wide: PWA install banner via `beforeinstallprompt` (dismiss persisted).

Tabs:
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
| Vectors | ChromaDB (daily prune) |
| Storage | local OR boto3 (S3/R2/B2/MinIO/Wasabi) |
| Auth | bcrypt 4.0.1 PINNED + passlib 1.7.4 + itsdangerous + phonenumbers |
| QR | pyzbar 0.1.9 + opencv-python 4.10.0.84 |
| Image | Pillow 11.1.0 + pillow-heif + imagehash + PyMuPDF |
| HTTP | httpx 0.28.1 |
| Parse | beautifulsoup4 4.12.3 |
| Rate limit | slowapi 0.1.9 (per-user keying) |
| Deploy | Docker multi-stage + Caddy 2-alpine (auto Let's Encrypt) |

## Configuration

| Variable | Default | Required |
|----------|---------|----------|
| `OPENROUTER_API_KEY` | — | YES |
| `SESSION_SECRET` | — | YES, ≥32 chars |
| `SUPER_ADMIN_EMAIL` | — | YES |
| `SUPER_ADMIN_PASSWORD` | — | YES |
| `SUPER_ADMIN_NAME` | "Super Admin" | |
| `SESSION_DAYS` | 14 | |
| `COOKIE_SECURE` | auto | `true` in prod |
| `CORS_ORIGINS` | localhost | comma-sep |
| `MAX_UPLOAD_BYTES` | 104857600 | 100MB |
| `MAX_IMAGE_PIXELS` | 100000000 | PIL bomb guard |
| `RATE_LIMIT_ENABLED` | true | |
| `STORAGE_BACKEND` | local | `s3` for cloud |
| `S3_BUCKET / S3_ENDPOINT_URL / S3_REGION / S3_PREFIX / S3_PUBLIC_BASE_URL` | — | for s3 |
| `DOMAIN` | kontact.example.com | Caddy TLS |
| `VISION_MODEL` | google/gemini-3.1-flash-lite-preview | |
| `EMBEDDING_MODEL` | openai/text-embedding-3-small | |
| `MAX_WORKERS` | 8 | extraction concurrency |
| `PORT` | 8090 | |

## Hardening landmarks (this session — 35 items)

### 🔴 5 CRITICAL security
- C1 `SESSION_SECRET` rotated + enforce ≥32 chars at startup
- C2 CORS env-driven; no wildcard with credentials
- C3 UUID strict-validated before TEMP VIEW SQL interpolation
- C4 Path traversal: realpath + `_safe_under(UPLOADS_DIR)` + null-byte block
- C5 Image ownership: owner_uuid join, non-admin can't see others' images

### 🟠 8 HIGH
- H1 Upload size cap (streaming check, 413 mid-stream)
- H2 PIL bomb guard `MAX_IMAGE_PIXELS=100M`
- H3 MIME allowlist + safe filename sanitizer
- H4 OpenRouter 3× exp-backoff retry on 429/5xx/network
- H5 `PRAGMA foreign_keys=ON` + dropped UNIQUE file_hash (FK collision)
- H7 Cookie `secure` env-driven
- H8 ChromaDB `prune_orphans` daily cron + `delete_by_folder` on batch delete
- (H6 passlib bump deferred — 1.7.4 + bcrypt 4.0.1 stable)

### 🟡 5 MEDIUM
- M1 Specific exception types in pipeline (log w/ context)
- M2 slowapi per-user keying (login 10/min/IP, upload 60/min/user, chat 120/min/user)
- M3 `/api/config` already gated
- M4 PDF page cap 200 + PIL pixel cap
- M5 `get_chat_history` strict `user_uuid` (removed `OR IS NULL` leak)

### 🐛 4 functional bugs
- **B1 GPS EXIF**: extractor wasn't propagating loader meta + file_hash UNIQUE collision blocked inserts. Fixed both. Test: B_gps.jpg → gps_lat=31.2304, country=中国, city=上海市.
- **B3 blur hallucination**: F_blur.jpg invented `$8,850` for real `$4,850`. Loader now pre-computes blur; extractor short-circuits, no fake products.
- **Messengers agg empty**: now reads flat platform cols + JSON blob.
- **WhatsApp invite parser**: `wa.me/qr/CODE` was extracting "qr" as phone. Now detects `/qr/` and `/message/` patterns.

### 🐛 +1 functional bug
- **`crypto.randomUUID()` LAN failure**: throws on http://192.168.x.x (non-secure context). Silent enqueue crash → upload tray never appeared. Fixed via `makeId()` fallback with Date.now+Math.random.

### ✨ 25 features
- **URL profile resolver** (SSRF-safe JSON-LD/OG extraction; tested w/ GitHub QR → "Linus Torvalds")
- **ChromaDB pruner** (daily cron + cascade delete)
- **Email-only login** (frontend locked, backend rejects non-email + ignores PIN)
- **Auto-submit upload + auto-redirect to /queue** (one-tap mobile)
- **Per-user queue privacy** (queue_batches filtered)
- **Backup + restore scripts** (single-archive snapshot)
- **S3 storage backend** (boto3, AWS/R2/B2/MinIO/Wasabi, migrate_to_s3.py)
- **13 new QR/barcode formats**: MeCard, VEVENT (→meeting row), GeoURL, WiFi, tel/mailto/sms, EPC SEPA, UPI, PIX, Bitcoin, Ethereum, Threads, Kakao pf.kakao.com, plus 1D barcodes via pyzbar symbology
- **Trade-show grouping** (column + form input + /api/aggregations/trade-shows)
- **AI auto-tagging** (heuristic 3-6 tags applied after every insert)
- **Currency normalization** (parse_price → currency + price_amount cols)
- **Contact merge + dedup** (/api/contacts/duplicates + /merge + vCard download)
- **Quick filters** (/api/data?trade_show=&country=&has_qr=&has_gps=)
- **PWA install banner** (beforeinstallprompt + dismissible)
- **Image lightbox in queue** (click thumb → full image + side panel)
- **Profile page + self-service password change** (/profile, POST /api/auth/change-password requires current_password; admin reset via /users)
- **PDF async raster + placeholder queue row** (instant batch visibility, no UI hang)
- **Floating upload tray** (global UploadQueueState + UploadTray component; non-blocking, cross-route, parallel=2)
- **Client-side image compression** (Fast mode toggle, createImageBitmap + OffscreenCanvas, 2000px max @ q=0.85, ~95% bandwidth saved)
- **Two-button upload UI** (Take picture + Upload, mobile compact, above-fold)
- **Image lightbox in /data Cards** (click thumb → modal, separate from row expand)
- **Categories tab image grids** (per-category thumbnail sections, lightbox, fallback to image_type for no-product docs)
- **Gallery group-by toggle** (All / By category / By company / By show + multi-select + bulk download)
- **AI auto-categorize products** (POST /api/categories/auto, LLM batch 12, fills empty categories)
- **Excel 8-sheet export** (Documents / Products w/ currency / Contacts / Companies / Categories / Specs / Gallery / Summary, bold+frozen headers, auto-width)
- **Blur threshold env-overridable** (default 20, was 100 → false positives on compressed JPEGs)

## Pitfalls

- **Login is email + password only** — phone/PIN paths removed. `users.pin_hash` exists in DB but never read. Don't re-enable PIN without rate-limit tightening (4-digit space is brute-forceable).
- **`crypto.randomUUID()` requires secure context** — throws on `http://192.168.x.x` LAN IPs. Use `makeId()` helper in `uploadQueue.svelte.ts` for any client-side ID generation. Localhost + HTTPS are fine.
- **PDF rasterization is async** — request handler inserts a placeholder queue row (file_name=`<pdf>.pdf`) so `/api/queue/batches` shows the batch instantly. Background `_split_pdfs_then_process` rasterizes pages then deletes the placeholder via `db.queue_delete_by_id`. Dispatched via `asyncio.create_task`, NOT `BackgroundTasks` (uvicorn holds connection on BackgroundTasks).
- **Blur threshold lowered to 20** (was 100). Client-compressed JPEGs (q=0.85, 2000px) score lower Laplacian variance. Env override: `BLUR_THRESHOLD`.
- **Bcrypt 4.0.1 PINNED** — passlib 1.7.4 breaks with bcrypt 5.x ("password cannot be longer than 72 bytes").
- **INSERT OR REPLACE forbidden** — FK to products/contacts cascades to constraint failure. Use upsert by (folder, source_file) only.
- **`file_hash` index** — plain (not UNIQUE) to avoid REPLACE collision when same image uploaded in different batches.
- **Caddy profile opt-in** — `docker compose --profile https up -d`. Default `docker compose up` = just kontact on 8090.
- **WhatsApp `wa.me/qr/<code>`** — phone NOT extractable without authenticated WA session (ToS-violating). Stores invite deeplink.
- **Blurry images** — extractor SKIPS LLM call, marks `image_type=blurry`. Saves tokens + prevents hallucination.
- **TEMP VIEW lifecycle** — created per chat-tool call, dropped via DROP VIEW IF EXISTS. UUID validate critical (defense in depth).
- **Background EXIF** — server-side `extract_exif()` runs in container; if browser strips EXIF, client-side `exifr@7.1.3` sidecar fills gaps.
- **slowapi per-user keying** — uses session cookie UUID. Falls back to IP if no auth cookie (login).

## Capacity

| Team size | Action |
|-----------|--------|
| 1–10 | as-is, single uvicorn worker |
| 10–50 | Dockerfile `--workers 4` |
| 50–500 | migrate SQLite → Postgres |
| 500+ | multi-container + Redis + Postgres + S3 + pgvector |

## Test fixtures

`/tmp/kontact_test/make_fixtures.py` generates A–V QR test images:
- A_catalog plain page, B_gps with EXIF GPS, C_qr_url, D_qr_vcard, E_qr_wechat
- F_blur, G_dup, H_qr_github (URL resolver test)
- I_qr_example, J_qr_mecard, K_qr_vevent, L_qr_geo
- M_qr_wifi, N_qr_tel, O_qr_email, P_qr_sms
- Q_qr_upi, R_qr_epc, S_qr_btc, T_qr_kakao
- U_qr_zalo, V_qr_threads

Regenerate: `/Users/rahulgupta/.venv/bin/python3 /tmp/kontact_test/make_fixtures.py`

## Quick smoke test

```bash
docker compose up -d --build kontact && sleep 8

curl -s -c /tmp/jar -X POST http://localhost:8090/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin@kontact.local","secret":"KontactAdmin2026!"}' | jq .uuid

curl -s -b /tmp/jar -X POST http://localhost:8090/api/upload \
  -F "files=@/tmp/kontact_test/B_gps.jpg" \
  -F "trade_show=CES 2026"

sleep 8

docker compose exec kontact python3 -c "
import sqlite3; c=sqlite3.connect('/app/data/kontact.db')
for r in c.execute('SELECT source_file, gps_lat, country, city, trade_show FROM documents ORDER BY id DESC LIMIT 3'):
    print(r)
"
```

## Deploy

```bash
# Dev (HTTP only, port 8090)
docker compose up -d --build kontact

# Prod (HTTPS via Caddy)
# Set in .env: DOMAIN=, COOKIE_SECURE=true, CORS_ORIGINS=https://yourdomain
docker compose --profile https up -d

# Verify
curl http://localhost:8090/health
docker compose logs -f kontact
```
