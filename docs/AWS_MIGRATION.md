# KONTACT → AWS ECS Fargate Migration Runbook

**Goal:** move KONTACT to AWS containers with **zero user impact** — no lost data, no lost UUIDs, no password resets, no forced re-login (optional), minimal downtime.

**Golden rule:** logins, users, passwords, roles, and all catalog data live in **one file — `kontact.db`**. Move that file (plus `uploads/` → S3) and everything follows. bcrypt password hashes are portable → **users keep their existing passwords**.

This runbook covers **Track A — SQLite on EFS, single Fargate task** (recommended first move: lowest risk, days not weeks, ~30-user ceiling). Track B (RDS Postgres + pgvector) is summarized at the end for when scale forces it.

---

## 0. What counts as "user impact" — and how we avoid each

| Possible impact | Cause | Prevention |
|-----------------|-------|------------|
| Users must re-register | users table not moved | move `kontact.db` (contains `users`) |
| Passwords stop working | hashes lost / re-hashed | copy `users.password_hash` verbatim (bcrypt string) |
| Everyone force-logged-out | `SESSION_SECRET` changed | **keep the same `SESSION_SECRET`** in Secrets Manager |
| Lost photos | uploads not migrated | push `uploads/` → S3 before cutover |
| Lost chat history / IDs | partial DB copy | copy whole `.db` after WAL checkpoint |
| Broken images in UI | storage backend mismatch | set `STORAGE_BACKEND=s3` + S3_* envs |
| Downtime | naive stop-then-move | parallel build + DNS cutover, ≤ minutes write-freeze |
| Stale RBAC nav | old frontend bundle | image built from latest `main` (commit ≥ `301e988`) |

---

## 1. Pre-flight inventory

Confirm what's on the live box before touching anything.

```bash
# row counts — record these numbers, you will match them post-migration
docker compose exec kontact python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/app/data/kontact.db')
for t in ['users','documents','products','contacts','chat_history',
          'tags','document_tags','notes','meetings','events',
          'queue','audit_events']:
    try:
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t:16} {n}")
    except Exception as e:
        print(f"{t:16} (missing) {e}")
PY

# users + roles — must match exactly after move
docker compose exec kontact python3 -c \
  "import sqlite3;[print(r) for r in sqlite3.connect('/app/data/kontact.db').execute('SELECT name,email,role,is_active FROM users')]"

# upload size → S3 transfer estimate
docker compose exec kontact du -sh /app/data/uploads
```

Record `users` count + the full user/role list. This is your acceptance check.

---

## 2. Provision AWS (no cutover yet — old box stays live)

Everything here is built **alongside** the running system. Users see nothing.

1. **ECR** — repo `kontact`.
2. **S3 bucket** — `kontact-uploads-prod` (block public access ON; app serves via presigned URLs).
3. **EFS** — filesystem + access point at `/kontact` (POSIX uid/gid matching container user). Holds `kontact.db` + `extractions/` + `*.json`. NOT uploads (those go to S3).
4. **Secrets Manager** — secret `kontact/env` holding the FULL `.env` contents. **Copy `SESSION_SECRET`, `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD` exactly from the old `.env`** (this is what keeps sessions + admin valid). Add `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`.
5. **ALB** — HTTPS:443, ACM cert for `citykontact.citygpt.xyz`.
   - **Idle timeout = 300s** (SSE chat stream dies otherwise).
   - Target group health check → `GET /health`.
6. **ECS cluster** + **task definition** (see §3) + **service** `desired=1`, **`maximumPercent=100`, `minimumHealthyPercent=0`** (guarantees ECS never runs two tasks on the same EFS SQLite file during deploys).
7. **CloudWatch** log group `/ecs/kontact`.

> ⚠️ **Single task is mandatory on Track A.** SQLite + ChromaDB are single-process. Two Fargate tasks on one EFS `.db` → `database is locked` + possible corruption. Lock the service to one task. Autoscaling = Track B only.

---

## 3. Build + push image (from latest `main`)

Image must include the RBAC fix (commit ≥ `301e988`) so admins don't see Settings.

```bash
git checkout main && git pull          # ensure 301e988 present
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR
docker build -t kontact:latest .
docker tag kontact:latest $ECR/kontact:latest
docker push $ECR/kontact:latest
```

Task definition essentials:
```jsonc
{
  "cpu": "1024", "memory": "2048",
  "containerDefinitions": [{
    "name": "kontact",
    "image": "$ECR/kontact:latest",
    "portMappings": [{ "containerPort": 8090 }],
    "mountPoints": [{ "sourceVolume": "data", "containerPath": "/app/data" }],
    "secrets": [ /* pull every key from Secrets Manager kontact/env */ ],
    "logConfiguration": { "logDriver": "awslogs",
      "options": { "awslogs-group": "/ecs/kontact", "awslogs-region": "$REGION",
                   "awslogs-stream-prefix": "kontact" } }
  }],
  "volumes": [{
    "name": "data",
    "efsVolumeConfiguration": {
      "fileSystemId": "$EFS_ID",
      "transitEncryption": "ENABLED",
      "authorizationConfig": { "accessPointId": "$EFS_AP_ID", "iam": "ENABLED" }
    }
  }]
}
```

Do **not** start the service against live DNS yet. Test it on the raw ALB DNS name first (§5).

---

## 4. Data migration (the careful part)

### 4a. Photos → S3 (do this FIRST — can run while old box is live, idempotent)

```bash
# on the old box, with S3_* set in .env
docker compose exec kontact python3 migrate_to_s3.py
```
`migrate_to_s3.py` walks `data/uploads/`, skips already-uploaded files (head_object check). Safe to run repeatedly. Folder names = document keys → preserved exactly, so image URLs keep resolving.

### 4b. Freeze writes (short window — this is the only "downtime")

Pick a low-traffic window. To make the write-freeze near-zero, optionally put the old box in read-only by stopping the queue/upload, or just accept a 2–5 min window.

```bash
# checkpoint WAL so the single .db file is fully consistent (no -wal/-shm needed)
docker compose exec kontact python3 -c \
 "import sqlite3;sqlite3.connect('/app/data/kontact.db').execute('PRAGMA wal_checkpoint(TRUNCATE)')"

# full backup = your rollback artifact
./backup.sh    # → backups/kontact-<timestamp>.tar.gz  (db + uploads + extractions + .env manifest)
```

### 4c. Seed EFS

Copy `kontact.db`, `extractions/`, `memories.json`, `feedback.json` onto the EFS access point. Three ways — pick one:

- **Temp EC2 + mount EFS** (simplest): mount EFS, `aws s3 cp` the backup down (or `scp` from old box), extract `kontact.db` + `extractions/` into `/kontact`.
- **DataSync**: S3/EFS task.
- **One-shot ECS task**: same image, override command to pull the tarball from S3 and unpack into `/app/data`.

Do **NOT** copy `chroma/` — it rebuilds automatically (§5). Copying a stale/locked Chroma store risks corruption.

---

## 5. Boot + verify on ALB DNS (BEFORE touching live domain)

```bash
aws ecs update-service --cluster kontact --service kontact --desired-count 1
```

On startup the app **auto-reindexes ChromaDB from `extractions/*.json`** onto the task's local disk — vectors rebuild fresh and deterministic (same IDs `{folder}/{source}/product_i`). One task → safe.

Smoke test against the **ALB DNS name** (e.g. `kontact-alb-123.elb.amazonaws.com`), not the live domain:

```bash
ALB=https://kontact-alb-xxxx.$REGION.elb.amazonaws.com

# 1. health
curl -s $ALB/health

# 2. LOGIN with a real existing user + their existing password → MUST succeed (proves bcrypt hashes carried)
curl -s -c /tmp/jar -X POST $ALB/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"winwintint@cityholdings.com.mm","secret":"<their real pw>"}' | jq .role

# 3. counts MATCH the §1 numbers
curl -s -b /tmp/jar $ALB/api/stats | jq

# 4. open a known document UUID → image must load (from S3) + chat returns vector hits
# 5. confirm RBAC: log in as an admin → Settings + Sync tabs ABSENT (proves new bundle)
```

Acceptance gate — all must pass:
- [ ] `users` count + role list match §1 exactly
- [ ] a real user logs in with their **old** password (no reset)
- [ ] document/product/contact counts match §1
- [ ] images load from S3
- [ ] chat returns answers (vectors rebuilt)
- [ ] admin user does NOT see Settings/Sync; super_admin does

If any fail → fix on AWS side, old box is still serving users untouched.

---

## 6. Cutover (zero / near-zero impact)

Only after every box in §5 is ticked.

1. Lower DNS TTL on `citykontact.citygpt.xyz` to 60s **a day before** (so cutover propagates fast).
2. Repeat the §4b freeze + a final **incremental** `kontact.db` copy to EFS (captures writes since the first seed). Keep this window tiny — minutes.
3. Point `citykontact.citygpt.xyz` → ALB.
4. Watch CloudWatch logs + re-run the §5 smoke test against the **live domain**.
5. Because `SESSION_SECRET` is unchanged, **existing user cookies stay valid → users are not logged out.** They notice nothing.

> If you chose to rotate `SESSION_SECRET` (more secure), the only impact is everyone logs in once more — passwords still work. Decide deliberately.

---

## 7. Post-cutover

```bash
# clear stale login throttle so nobody is locked from old failed attempts
# (run via one-shot ECS exec or include in seed step)
DELETE FROM login_attempts;
```

- Keep the old box **running but read-only** for ~1 week as instant rollback.
- Keep the `backup.sh` tarball off-box (S3, versioned).
- Enable EFS automatic backups + S3 versioning.
- Set a CloudWatch alarm on `database is locked` log pattern → catches accidental 2-task runs.

### Rollback (if cutover goes wrong)
1. Point DNS back to the old box (still live). Done — users back on the old system within one TTL.
2. Old box never lost data; the AWS side was additive.

---

## 8. Track B — RDS Postgres + pgvector (future, at scale)

Switch when you cross ~30 concurrent users or need autoscaling / zero-downtime deploys. SQLite on EFS cannot do multi-task.

**Still zero password impact** — the migration script copies `users.password_hash` (bcrypt string) verbatim and preserves all UUIDs.

Required code port (one-time):
- FTS5 `documents_fts` + triggers → Postgres `tsvector` + GIN index
- ChromaDB `PersistentClient` → `pgvector` column + cosine index (drops the separate Chroma service)
- Delete `write_lock()` + all 42 `@serialized_write` decorators — Postgres handles concurrency natively
- `?` placeholders → `%s` (psycopg); drop `busy_timeout`/`INSERT OR REPLACE` workarounds
- `visibility_clause()` logic unchanged

Data move (UUID + hash preserving, idempotent):
```python
src = sqlite3.connect("kontact.db")
dst = psycopg.connect(PG_DSN)
# users FIRST (FK parent), then children: documents → products/contacts → rest
TABLES = ["users","documents","products","contacts","chat_history",
          "tags","document_tags","notes","meetings","events",
          "queue","audit_events","merge_proposals","merge_blacklist"]
for t in TABLES:
    cols = [c[0] for c in src.execute(f"SELECT * FROM {t} LIMIT 0").description]
    rows = src.execute(f"SELECT * FROM {t}").fetchall()
    if not rows: continue
    ph = ",".join(["%s"]*len(cols))
    dst.cursor().executemany(
        f"INSERT INTO {t} ({','.join(cols)}) VALUES ({ph}) ON CONFLICT (uuid) DO NOTHING",
        rows)
dst.commit()
# skip documents_fts (rebuild tsvector); skip vectors (rebuild from extractions)
```
Then point `DATABASE_URL` at RDS, set service `desired=N`, attach autoscaling, drop the EFS volume. Photos already on S3 from Track A — no change.

---

## Quick reference — the three things that keep users unaffected

1. **`kontact.db` moves whole** → users, roles, passwords (bcrypt), chat, all data come with it.
2. **`SESSION_SECRET` unchanged** → live cookies stay valid → no forced logout.
3. **`uploads/` → S3 with same folder keys** → images keep resolving.

Everything else (Chroma vectors, FTS) is rebuilt, not migrated.
