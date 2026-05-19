# KONTACT

**Catalog vision RAG agent for trade shows.** Snap photos, scan QRs, extract structured data with multi-agent AI, and chat with an SQL-aware agent that remembers who you met.

Multi-tenant. Hardened. Production-shape. One-tap mobile.

---

## Quick start

```bash
git clone https://github.com/raahulgupta07/airg-kontact.git
cd airg-kontact
cp .env.example .env

# Edit .env — set these 4 lines minimum
#   OPENROUTER_API_KEY=sk-or-v1-...
#   SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
#   SUPER_ADMIN_EMAIL=admin@yourdomain.com
#   SUPER_ADMIN_PASSWORD=strong-password

docker compose up -d --build kontact
# → http://localhost:8090
```

## Test credentials (dev)

```
URL:       http://localhost:8090
Phone:     http://<your-LAN-ip>:8090  (same WiFi)
Email:     admin@kontact.local
Password:  KontactAdmin2026!
```

---

## What it does

1. **Capture** — phone camera / library picker / file picker / PDF / drag-drop. Browser geolocation + EXIF sidecar.
2. **Auto-classify + extract** — 8 specialized vision agents (product page, contact card, QR card, business card, price list, brochure, certification, other).
3. **Enrich**
   - **EXIF**: GPS, camera, lens, ISO, exposure, software, sub-second
   - **Geocode**: country + city + address via Nominatim
   - **Image quality**: perceptual hash + Laplacian blur + near-dup clustering
   - **QR/barcode decode** (40+ formats — see matrix below)
   - **URL profile resolution** (JSON-LD + OG + microdata; SSRF-guarded)
4. **Tag** — heuristic auto-tags: industry, region, content type, signal flags
5. **Normalize** — products/contacts in queryable tables with UUIDs, currency + price_amount parsed out
6. **Chat** — SQL tool loop (Gemini 3.1 Flash Lite via OpenRouter), per-user history, streaming, image citations
7. **Browse** — 20-tab grouped UI, Leaflet map, lightbox, vCard export, contact merge, quick filters

---

## QR + barcode support (40+ formats)

| Category | Formats |
|----------|---------|
| **Contact cards** | vCard 3.0/4.0, MeCard (Japan/KR) |
| **Messengers** | WhatsApp (E.164 / invite-code / business message), WeChat URL, Viber, Telegram (tg://, t.me), Line, Signal, Kakao (incl `pf.kakao.com`), Zalo (Vietnam), Skype, Messenger, Instagram, Snapchat, Discord, Threads |
| **Communication** | `tel:`, `mailto:`, MATMSG, `smsto:`, `sms:` |
| **Connectivity** | WiFi (`WIFI:T:WPA;S:...;P:...;`) |
| **Location** | GeoURL (`geo:lat,lng?q=...`) — overrides GPS if EXIF missing |
| **Calendar** | iCalendar VEVENT → auto-creates meeting row |
| **Payments** | EPC SEPA (EU bank), UPI (India), PIX (Brazil), Bitcoin, Ethereum |
| **Profile URLs** | any HTTPS URL — fetched, parsed via JSON-LD + OG + microdata |
| **1D barcodes** | EAN13, EAN8, UPCA, UPCE, CODE128, CODE39, ITF (via pyzbar symbology) |
| **Plain text** | stored as-is |

---

## Auth

**Email + password only.** Phone/PIN auth removed for simplicity.

- bcrypt 4.0.1 (passlib pinned)
- HttpOnly cookie sessions, 14-day, itsdangerous-signed
- `COOKIE_SECURE` env-driven for HTTPS prod
- 5 fails / 15 min → 30-min lockout
- Per-user rate limits: 10/min login, 60/min upload, 120/min chat (slowapi)
- Multi-tenant: `visibility_clause()` enforces `owner_uuid` filter on every visible query; `super_admin` sees all

Super admin bootstraps from `.env`:
```bash
SUPER_ADMIN_EMAIL=admin@yourdomain.com
SUPER_ADMIN_PASSWORD=<strong>
SUPER_ADMIN_NAME=Your Name
```
Additional users created via `/users` admin UI.

---

## Workflow features

### Trade-show grouping
Tag every upload with a show label (e.g. "CES 2026"). Persists in localStorage on upload page. Filter `/data` by `?trade_show=<name>`. Aggregation: `/api/aggregations/trade-shows`.

### AI auto-tagging
Each ingested document gets 3–6 heuristic tags applied automatically:
- Content type: `product`, `contact-card`, `pricing`, `blurry`
- Industry: `pumps`, `electronics`, `machinery`, `pharma`, `solar`, `auto`, `textile`, `food`, `chemicals`, `packaging`, `logistics`
- Region: `region-asia`, `region-eu`, `region-na`
- Signal flags: `has-qr`, `has-messenger`, `has-phone`, `has-email`, `has-pricing`

### Currency normalization
Free-form prices (`$4,850 USD`, `€ 1.234,50`, `RMB 12,000`, `₹999/-`) parsed into:
- `products.currency` — ISO 4217 code (USD, EUR, CNY, INR, JPY, GBP, …)
- `products.price_amount` — numeric value

### Contact deduplication + merge
- `GET /api/contacts/duplicates` → groups by `phone_e164` or `email` match
- `POST /api/contacts/merge` → moves notes/meetings, deletes drop
- `GET /api/contacts/{uuid}/vcard` → RFC 6350 `.vcf` (opens in phone Contacts)
- `GET /api/export/vcards.zip` → bulk vCards

### Quick filters
```
/api/data?trade_show=CES%202026&country=China&has_qr=1&has_gps=1
```

### Image lightbox (everywhere)
Click any thumbnail in `/queue`, `/data` (Cards / Categories / Gallery) → full image popup with side panel (filename, type chip, company, trade-show chip, contact, products with prices, GPS, camera, date, sharpness score). Esc / backdrop / × closes. PDF page-grouping with prev/next arrows. Mobile responsive.

### Gallery with grouping + multi-select + bulk download
- Toolbar: **All / By category / By company / By show**
- ✨ AI categorize button → uses LLM to fill missing categories
- **Select** mode → checkbox each thumb → **Download (N)** triggers per-file downloads
- Category overlay badge on every thumbnail in flat view

### Floating upload tray (non-blocking)
- Pick photo / PDF → enqueues to global tray (bottom-right or bottom on mobile)
- Pill shows `N uploading · 72%` + progress bar; tap to expand list
- User can keep tapping Camera/Library — queue parallelism = 2
- Survives route navigation (visible across all tabs)
- Auto-hides 3s after all done
- Re-fires queued jobs on `window 'online'` event (offline recovery)
- Each job: queued → compressing → uploading → done/error
- Cancel/retry/view buttons per row

### Two-button upload UI
Compact mobile layout — both buttons above the fold:
- **Take picture** (rear camera, capture=environment)
- **Upload** (photos OR PDF)
Trade-show input + Fast mode toggle collapse into `<details>` "Options" panel.

### AI auto-categorize
`POST /api/categories/auto` → batches 12 products/LLM call → fills `products.category` with concise 2-4 word labels. Two modes: only-uncategorized (safe) or force-all (overwrites). Used by both `/data Categories` tab and `/data Gallery` toolbar.

### Comprehensive Excel export (8 sheets)
"Excel ⬇" button top-right of `/data` → single `.xlsx`:
- Documents (every catalog page w/ EXIF + GPS + uploader)
- Products (with parsed `currency` + `price_amount`)
- Contacts (with messenger handles)
- Companies (aggregated)
- Categories (counts + top companies)
- Specs (one row per spec)
- Gallery (image inventory w/ URLs)
- Summary (per-company rollup)

Bold + frozen headers, auto-sized columns.

### PWA install
Bottom banner with "Install" button on Chrome/Edge. Dismissal persisted in localStorage.

---

## Architecture

```
Phone Camera / Files / PDF / Sync Watcher
         ↓
Upload (size + MIME + filename + PIL-bomb guards, trade_show tag)
         ↓
Queue (SQLite, owner_uuid + trade_show per row)
         ↓
Loader: EXIF + 40+ QR/barcode parsers + phash + blur
         ↓
Extractor:
    is_blurry? → skip LLM, mark blurry, no hallucination
    else → Classifier → Specialized agent (Gemini via OpenRouter)
         ↓
    Merge QR + URL-resolver enrichment for URL-type QRs
         ↓
Insert: documents + products (+currency/price_amount) + contacts +
        messengers + meetings (from VEVENT) + audit
         ↓
Auto-tag (industry, region, signal flags)
         ↓
Storage: local disk OR S3 (mirror via storage.save_file)
         ↓
Index: ChromaDB + FTS5
         ↓
Agent: SQL tool loop + per-user memory + streaming + retry-on-429
```

---

## Database (12 tables, FK enforced, WAL)

```
users              uuid, email, phone_e164, password_hash, role, is_active
documents          50+ cols (EXIF, geo, quality, audit, trade_show)
products           normalized + currency + price_amount
contacts           normalized + messenger columns
queue              with owner_uuid + trade_show
documents_fts      FTS5 virtual
chat_history       per-session + user_uuid (strict scope)
audit_events       upload/login/edit/delete/share/merge
login_attempts     throttle log
tags + document_tags + notes + meetings + events    workspace CRUD
```

---

## API (50+ endpoints)

```
# Auth
POST   /api/auth/login              email + password, 10/min/IP
POST   /api/auth/logout
GET    /api/auth/me

# Users (admin-only)
GET POST PATCH DELETE /api/users{/uuid}

# Upload + queue
POST   /api/upload                  60/min/user, accepts trade_show form field
GET    /api/queue/batches           per-user (admin: all)
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
GET    /api/products                with currency + price_amount
GET    /api/contacts
GET    /api/contacts/duplicates     dedup suggestions
POST   /api/contacts/merge          keep_uuid + drop_uuid
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

# AI helpers
POST   /api/categories/auto         auto-categorize products via LLM
                                    body: {force: bool}

# Workspace CRUD
{GET POST PATCH DELETE} /api/{tags,notes,meetings,events}

# Image (auth + ownership + realpath)
GET    /api/image/{folder}/{filename}    local FileResponse OR S3 presigned redirect

# Export
GET    /api/export/{xlsx,csv,json}

# Other
POST   /api/feedback
GET    /api/memories
GET    /api/config                  auth-gated
GET    /health                      public
```

---

## Security

| Layer | Control |
|-------|---------|
| Secrets | `SESSION_SECRET` ≥32 chars enforced at startup; placeholders fail. `.env` gitignored. |
| CORS | `CORS_ORIGINS` env, no wildcard w/ credentials |
| SQL injection | UUID strict regex + `uuid.UUID()` parse before TEMP VIEW interpolation |
| Path traversal | `os.path.realpath` + `_safe_under(UPLOADS_DIR)` + null-byte block |
| Image ownership | `owner_uuid` join on every serve (non-admin) |
| Upload | MIME allowlist + 100MB cap + safe filename + PIL 100MP bomb guard + PDF 200-page cap |
| SSRF | `url_resolver.py` blocks private/loopback/link-local IPs + `.local` hosts |
| Rate limit | slowapi per-user keying (so shared NAT doesn't share quotas) |
| DB | `PRAGMA foreign_keys=ON` on every connection, WAL, 30s busy_timeout |
| LLM | OpenRouter 3× exp-backoff retry on 429/5xx |
| Storage | ChromaDB daily prune + cascade delete on batch removal |
| Privacy | `visibility_clause()` filters `owner_uuid` everywhere |
| Audit | `audit_events` table logs upload/login/edit/delete/share/merge |

---

## Storage backend (local or S3)

```bash
STORAGE_BACKEND=local                # default — data/uploads/ on disk
# OR
STORAGE_BACKEND=s3
S3_BUCKET=my-kontact-uploads
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_ENDPOINT_URL=                     # blank=AWS; set for R2/B2/MinIO
S3_REGION=us-east-1
S3_PREFIX=prod/
S3_PUBLIC_BASE_URL=                  # if bucket public
```

Image serve auto-switches: local backend streams via `FileResponse`, S3 backend redirects to presigned URL (10-min expiry).

Migration (one-time, idempotent):
```bash
docker compose exec kontact python3 migrate_to_s3.py
```

Tested with AWS S3, Cloudflare R2, Backblaze B2, MinIO, Wasabi.

---

## Backup + restore

```bash
./backup.sh                          # → backups/kontact-backup-YYYYMMDD-HHMMSS.tar.gz
./restore.sh <archive>               # idempotent restore on any server
```

Captures: SQLite DB (WAL-checkpointed) + ChromaDB + uploads + extractions + `.env`. Single archive, ~2MB on a fresh install.

Migrate to new server:
```bash
# OLD machine
./backup.sh
scp backups/kontact-backup-*.tar.gz user@new-server:/tmp/

# NEW machine
git clone https://github.com/raahulgupta07/airg-kontact.git
cd airg-kontact
./restore.sh /tmp/kontact-backup-*.tar.gz
docker compose up -d --build kontact
```

---

## Production deploy (HTTPS via Caddy)

```bash
# In .env
COOKIE_SECURE=true
CORS_ORIGINS=https://kontact.yourdomain.com
DOMAIN=kontact.yourdomain.com
SUPER_ADMIN_PASSWORD=<rotate>
SESSION_SECRET=<rotate>

# DNS: A/AAAA record → server IP, port 80+443 open
docker compose --profile https up -d
```

Caddy auto-issues Let's Encrypt cert.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI 0.115.6 + Python 3.12 |
| Frontend | SvelteKit 5 + Svelte 5 runes + Tailwind v4 |
| LLM | Gemini 3.1 Flash Lite via OpenRouter |
| Embeddings | OpenAI text-embedding-3-small via OpenRouter |
| DB | SQLite WAL + FTS5 |
| Vectors | ChromaDB (daily prune) |
| Storage | Local OR S3-compatible (boto3) |
| Auth | bcrypt 4.0.1 + passlib 1.7.4 + itsdangerous + phonenumbers |
| QR | pyzbar + opencv-python (rotation fallback) |
| Image | Pillow + pillow-heif + imagehash + PyMuPDF |
| HTTP | httpx |
| Parse | beautifulsoup4 |
| Rate limit | slowapi (per-user keying) |
| Deploy | Docker multi-stage + Caddy 2-alpine (auto Let's Encrypt) |
| PWA | manifest + service worker + install banner |

---

## Configuration reference

| Variable | Default | Purpose |
|----------|---------|---------|
| **Required** | | |
| `OPENROUTER_API_KEY` | — | LLM + embeddings |
| `SESSION_SECRET` | — | ≥32 chars; fails startup if missing/placeholder |
| `SUPER_ADMIN_EMAIL` | — | Bootstrap admin email (used for login) |
| `SUPER_ADMIN_PASSWORD` | — | Bootstrap admin password |
| **Optional** | | |
| `SUPER_ADMIN_NAME` | "Super Admin" | display name |
| `SESSION_DAYS` | 14 | cookie lifetime |
| `COOKIE_SECURE` | auto | `true` in prod (HTTPS) |
| `CORS_ORIGINS` | localhost | comma-sep; `*` disables credentials |
| `MAX_UPLOAD_BYTES` | 104857600 | 100MB per file |
| `MAX_IMAGE_PIXELS` | 100000000 | PIL bomb guard |
| `BLUR_THRESHOLD` | 20 | Laplacian var below this = blurry. Lower = more lenient. |
| `RATE_LIMIT_ENABLED` | true | slowapi toggle |
| `STORAGE_BACKEND` | local | `s3` for cloud |
| `S3_BUCKET / S3_*` | — | S3-compatible config |
| `DOMAIN` | kontact.example.com | Caddy TLS |
| `VISION_MODEL` | google/gemini-3.1-flash-lite-preview | |
| `EMBEDDING_MODEL` | openai/text-embedding-3-small | |
| `MAX_WORKERS` | 8 | extraction concurrency |
| `PORT` | 8090 | LAN dev port |
| `WECHAT_WATCH_DIR` | — | auto-start WeChat sync watcher |

---

## Capacity

| Team size | Action |
|-----------|--------|
| 1–10 | works as-is, single uvicorn worker |
| 10–50 | bump Dockerfile: `--workers 4` |
| 50–500 | migrate SQLite → Postgres |
| 500+ | multi-container + Redis + Postgres + S3 + pgvector |

---

## Commands

```bash
# Dev
docker compose up -d --build kontact
docker compose logs -f kontact

# Backup
./backup.sh

# Migrate uploads to S3 (after STORAGE_BACKEND=s3 + S3_* set)
docker compose exec kontact python3 migrate_to_s3.py

# Frontend hot reload (proxy /api → :8090)
cd frontend && npm run dev
```

---

## License

MIT.
