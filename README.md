# KONTACT — Catalog Vision RAG Agent

Snap photos of product catalogs at trade shows, scan QR codes (vCard, WhatsApp, WeChat, URL), extract structured data with multi-agent AI vision, and chat with an intelligent agent that runs SQL queries, remembers facts, cites sources with images, and knows who you met.

**Multi-tenant, hardened, production-shape.**

## What it does

1. **Upload** — Phone camera, file picker, PDF, drag-drop. Browser geolocation + client EXIF fallback for stripped images.
2. **Classify + Extract** — 8 specialized AI agents route + extract products, contacts, specs, prices, QR payloads.
3. **Enrich** —
   - EXIF: GPS, camera, lens, ISO, exposure, software, sub-second time
   - Reverse geocode → country, city, address
   - Perceptual hash + blur detection (blurry images skip LLM)
   - QR decode: vCard, WhatsApp, WeChat, Viber, Telegram, Line, Signal, URL
   - **URL QR resolver**: fetch landing page, parse JSON-LD + OG + microdata → person/company/phone/email
4. **Normalize** — Products, contacts, companies, messengers in queryable tables with UUIDs.
5. **Chat** — Agent with SQL tools, per-user history, streaming SSE, image citations, retry-on-429.
6. **Browse** — 20-tab UI (Catalog / Insights / Workspace): tables, gallery, Leaflet map, timeline, dedup clusters, exports.

## Quick start

```bash
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY, SUPER_ADMIN_PASSWORD, SESSION_SECRET
docker compose up -d --build kontact
# http://localhost:8090
```

Default super-admin login bootstraps from `.env`. Create more users from `/users`.

## Production deploy

```bash
# In .env
COOKIE_SECURE=true
CORS_ORIGINS=https://kontact.yourdomain.com
DOMAIN=kontact.yourdomain.com
SUPER_ADMIN_PASSWORD=<rotate>
SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')

# Caddy + Let's Encrypt
docker compose --profile https up -d
```

## Auth

**Email + password only.** Phone/PIN auth removed for simplicity.

| Field | Note |
|-------|------|
| Email | normalized lowercase; `type=email` browser validation |
| Password | bcrypt 4.0.1 (passlib pinned) |

Session = HttpOnly cookie, 14-day, signed (itsdangerous), HTTPS-secure when `COOKIE_SECURE=true`.

5 fails in 15 min → 30-min lockout. Rate limits: 10/min login, 30/min upload, 60/min chat.

Bootstrap super admin from `.env` on first start:
```bash
SUPER_ADMIN_EMAIL=admin@yourdomain.com
SUPER_ADMIN_PASSWORD=<strong>
SUPER_ADMIN_NAME=Your Name
```
Additional users created via `/users` admin UI (also email + password only).

## Architecture

```
Phone Camera / File Picker / PDF / Sync Watcher
        ↓
Upload (MIME + size + PIL bomb guards + safe filename)
        ↓
Queue (SQLite, owner_uuid per row)
        ↓
Loader: EXIF + QR + phash + blur
        ↓
Extractor:
    is_blurry? → skip LLM, mark blurry
    else → Classifier (Gemini 3.1 Flash Lite) → Specialized agent
                ↓
        Merge QR + url_resolver enrichment for URL-type QRs
        ↓
Insert: documents + products + contacts + messengers + audit
        ↓
Index: ChromaDB (vector) + FTS5 (lexical) + audit_events
        ↓
Agent: SQL tool loop + memory + streaming SSE
```

## Database (12 tables)

| Table | Purpose |
|-------|---------|
| `users` | accounts, roles, last_login |
| `documents` | catalog pages, 50+ columns (EXIF, geo, quality, audit) |
| `products` | normalized one-per-row |
| `contacts` | normalized one-per-row, messenger columns |
| `documents_fts` | FTS5 virtual table |
| `queue` | upload queue, owner_uuid |
| `chat_history` | per-session, scoped by user_uuid |
| `login_attempts` | throttle log |
| `audit_events` | upload/login/edit/delete/share/merge |
| `tags`, `document_tags`, `notes`, `meetings`, `events` | workspace CRUD |

`PRAGMA foreign_keys=ON`. WAL mode. 30s busy_timeout.

## Endpoints (50+)

```
/api/auth/{login,logout,me}                                 email + password
/api/users {GET POST PATCH DELETE}
/api/upload {POST}                                          form field: trade_show
/api/queue {GET}  /api/queue/batches  /api/queue/retry/{id} /api/batch/{id} {DELETE}
/api/chat {POST}  /api/chat/stream {SSE}  /api/chat/sessions  /api/chat/history/{sid}
/api/data?trade_show=&country=&has_qr=&has_gps=             quick filters
/api/products  /api/contacts  /api/dashboard
/api/search  /api/search/semantic
/api/contacts/duplicates                                    dedup suggestions
/api/contacts/merge {POST}                                  keep_uuid + drop_uuid
/api/contacts/{uuid}/vcard                                  .vcf download
/api/export/vcards.zip                                      bulk vCards
/api/aggregations/{locations,countries,timeline,cameras,messengers,
                   qr-codes,quality,duplicates,sync-sources,pricing,
                   map-points,trade-shows}
/api/tags /api/notes /api/meetings /api/events {CRUD}
/api/image/{folder}/{file}                                  realpath-checked, owner-scoped
/api/export/{xlsx,csv,json}
/api/feedback /api/memories /api/config (auth)
/health (public)
```

## Security

| Layer | Control |
|-------|---------|
| Secrets | `SESSION_SECRET` ≥32 chars, fails startup if placeholder. Live API key/admin password never in repo (`.env` gitignored). |
| CORS | env-driven origins, no wildcard with credentials |
| Auth | bcrypt 4.0.1 (passlib pinned), HttpOnly cookies, JWT-style timed token |
| Privacy | `visibility_clause()` filters `owner_uuid` on every query; chat history `user_uuid` strict; TEMP VIEW rewriter for chat SQL tool |
| Input | UUID strict-parse before SQL, MIME allowlist, 100MB size cap, PIL 100MP pixel cap, PDF 200-page cap |
| Network | SSRF guard in url_resolver (blocks private IPs, `.local`, loopback) |
| Path | image serve uses `realpath` + `_safe_under(UPLOADS_DIR)` |
| Rate | slowapi per-route |
| DB | FK ON, busy_timeout, WAL, `INSERT OR REPLACE` removed for FK safety |
| LLM | OpenRouter 3× retry on 429/5xx |
| Storage | ChromaDB daily prune + cascade delete on batch removal |

## EXIF + browser geo

`pipeline/loader.py:extract_exif` reads via PIL `getexif().get_ifd()`:
- GPS lat/lng/altitude/heading/speed (with unit conversion)
- DateTimeOriginal + sub-second
- Camera make/model, lens model, focal length, f-number, ISO, exposure time
- Orientation, dimensions, file size

Client-side fallback in `upload/+page.svelte`:
- `exifr@7.1.3` reads EXIF before browser strips it
- `navigator.geolocation` (8s timeout)
- `DeviceOrientationEvent` (iOS heading)
- Battery API + device signals JSON

Server merges in priority: EXIF > client EXIF sidecar > browser geo.

## QR + barcode support matrix

| Category | Formats |
|----------|---------|
| **Contact cards** | vCard 3.0/4.0, MeCard (Japan/KR) |
| **Messengers** | WhatsApp (`wa.me/<E164>`, `wa.me/qr/<code>`, `wa.me/message/<code>`), WeChat URL, Viber, Telegram, Line, Signal, Kakao (incl `pf.kakao.com`), Zalo, Skype, Messenger, Instagram, Snapchat, Discord, Threads |
| **Communication** | `tel:`, `mailto:`, MATMSG, `smsto:`, `sms:` |
| **Connectivity** | WiFi (`WIFI:T:WPA;S:...;P:...;`) |
| **Location** | GeoURL (`geo:lat,lng?q=...`) — overrides GPS if EXIF missing |
| **Calendar** | iCalendar VEVENT — auto-creates meeting row |
| **Payments** | EPC SEPA (EU bank), UPI (India), PIX (Brazil), Bitcoin, Ethereum |
| **Profile URLs** | any HTTPS URL — fetched, parsed via JSON-LD + OG + microdata |
| **1D barcodes** | EAN13, EAN8, UPCA, UPCE, CODE128, CODE39, ITF (via pyzbar symbology) |
| **Plain text** | stored as-is |

## URL profile resolver

`pipeline/url_resolver.py` — when a QR encodes a plain URL:
- SSRF guard (block private/loopback/link-local)
- httpx GET, 8s timeout, 2MB cap, 4 redirects
- Parse: JSON-LD Person/Organization/LocalBusiness → name/phone/email/address/jobTitle/sameAs
- Fallback: OG meta (title, site_name), `mailto:`/`tel:` links, regex on text
- Phone → E.164 via phonenumbers

Tested: GitHub profile → person + company + social URLs extracted.

## Frontend

SvelteKit 5 + Tailwind v4 + Svelte 5 runes. Routes:

| Route | Purpose |
|-------|---------|
| `/login` | email/phone + password/PIN, show-pw, remember me |
| `/upload` | hero camera + 3 inputs (camera/library/files) + EXIF/geo capture |
| `/queue` | batch list, inline expand, retry, delete |
| `/chat` | streaming SSE + SQL tool steps + citations + feedback + voice |
| `/data` | grouped 3-section nav: Catalog (7), Insights (10), Workspace (3) |
| `/users` | admin: CRUD users |

20 sub-tabs include ProductsTable, ContactsTable, CompaniesTable, CategoriesTable, SpecsTable, Gallery, LocationsMap (Leaflet), Timeline, Countries, Messengers, QrCodes, Quality, Duplicates, SyncSources, Cameras, Pricing, Tags, Notes, Meetings.

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI + Python 3.12 (3,500 LOC) |
| Frontend | SvelteKit 5 + Tailwind v4 (5,500 LOC) |
| LLM | Gemini 3.1 Flash Lite via OpenRouter |
| Embeddings | OpenAI text-embedding-3-small via OpenRouter |
| DB | SQLite WAL + FTS5 + 12 tables + UUIDs |
| Vectors | ChromaDB (daily prune) |
| Auth | bcrypt + passlib + itsdangerous + phonenumbers |
| QR | pyzbar + cv2 (with rotation fallback) |
| Image | Pillow + pillow-heif + imagehash + cv2 Laplacian |
| Rate limit | slowapi |
| Deploy | Docker multi-stage + Caddy (auto Let's Encrypt) |
| PWA | manifest + service worker (network-first) |

## Configuration (.env)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENROUTER_API_KEY` | — | required |
| `SESSION_SECRET` | — | ≥32 chars, fails startup if missing/placeholder |
| `SESSION_DAYS` | 14 | cookie lifetime |
| `COOKIE_SECURE` | auto | `true` in prod (HTTPS) |
| `CORS_ORIGINS` | localhost | comma-separated, no wildcard w/ credentials |
| `SUPER_ADMIN_{EMAIL,PASSWORD,NAME}` | — | bootstrap |
| `MAX_UPLOAD_BYTES` | 104857600 | 100MB per file |
| `MAX_IMAGE_PIXELS` | 100000000 | PIL bomb guard |
| `RATE_LIMIT_ENABLED` | true | slowapi toggle |
| `DOMAIN` | — | Caddy auto-TLS |
| `VISION_MODEL` | google/gemini-3.1-flash-lite-preview | |
| `EMBEDDING_MODEL` | openai/text-embedding-3-small | |
| `MAX_WORKERS` | 8 | extraction concurrency |
| `PORT` | 8000 | |

## Commands

```bash
# Dev
docker compose up -d --build kontact
docker compose logs -f kontact

# Test (synthetic fixtures + curl smoke)
python3 /tmp/kontact_test/make_fixtures.py  # see CLAUDE.md
curl -c jar -X POST localhost:8090/api/auth/login -H 'Content-Type: application/json' \
  -d '{"identifier":"admin@kontact.local","secret":"<pwd>"}'

# Frontend hot reload (proxy /api → :8090)
cd frontend && npm run dev
```

## Workflow features

### Trade-show grouping
Tag every upload with a show label (e.g. "CES 2026"). Persists in localStorage on upload page. Filter `/data` by `?trade_show=<name>`. Aggregation endpoint `/api/aggregations/trade-shows` returns counts.

### AI auto-tagging
Each ingested document gets 3-6 heuristic tags applied automatically:
- Content type: `product`, `contact-card`, `pricing`, `blurry`
- Industry: `pumps`, `electronics`, `machinery`, `pharma`, `solar`, …
- Region: `region-asia`, `region-eu`, `region-na` (from geocoded country)
- Signal flags: `has-qr`, `has-messenger`, `has-phone`, `has-email`, `has-pricing`

### Currency normalization
Free-form prices (`$4,850 USD`, `€ 1.234,50`, `RMB 12,000`, `₹999/-`) parsed into:
- `products.currency` — ISO 4217 code (USD, EUR, CNY, INR, …)
- `products.price_amount` — numeric value

### Contact deduplication + merge
- `/api/contacts/duplicates` groups by `phone_e164` or `email` match
- `/api/contacts/merge` moves children (notes, meetings) to the kept row and deletes the drop
- vCard download per contact: `GET /api/contacts/{uuid}/vcard` → `.vcf` → opens in phone Contacts

### Quick filters
`/api/data?trade_show=...&country=...&has_qr=1&has_gps=1` — server-side post-filter visible to user.

### Image lightbox
Click any thumbnail in `/queue` → full-image modal with side panel (filename, type chip, company, trade-show chip, contact, products with prices, GPS, camera, date). Esc/backdrop closes.

### PWA install
Bottom banner with "Install" button on Chrome/Edge. Stores dismissal in localStorage so it doesn't nag.

## Storage backend (local or S3)

`STORAGE_BACKEND=local` (default) — uploads live in `data/uploads/` on disk.

`STORAGE_BACKEND=s3` — mirror every upload to S3-compatible storage. Works with:
- AWS S3
- Cloudflare R2 (`S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com`)
- Backblaze B2 (`S3_ENDPOINT_URL=https://s3.<region>.backblazeb2.com`)
- MinIO (`S3_ENDPOINT_URL=http://minio:9000`)
- Wasabi

Image serve returns a presigned URL (10-min expiry) instead of streaming the file → CDN-friendly, multi-container safe.

```bash
# .env additions
STORAGE_BACKEND=s3
S3_BUCKET=my-kontact-uploads
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_REGION=us-east-1
S3_ENDPOINT_URL=                 # blank = AWS; set for R2/B2/MinIO
S3_PREFIX=prod/                  # optional
S3_PUBLIC_BASE_URL=              # set if bucket is public (skips presign)

# Migrate existing local uploads to S3 (one-time, idempotent)
docker compose exec kontact python3 migrate_to_s3.py
```

Cascading: deleting a batch removes both DB rows AND the S3 prefix.

## Backup + restore

```bash
./backup.sh                       # → backups/kontact-backup-YYYYMMDD-HHMMSS.tar.gz
./restore.sh <archive>            # restore on any server
```

Captures: SQLite DB (WAL-checkpointed) + ChromaDB + uploads + extractions + `.env`. See [`CLAUDE.md`](CLAUDE.md) for full details.

## License

MIT.
