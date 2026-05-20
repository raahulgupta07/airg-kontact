import sqlite3, json, os, hashlib, threading, queue, atexit
from uuid import uuid4
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import config

DB_PATH = os.path.join(config.DATA_DIR, "kontact.db")

# ─── Connection pool (SQLite WAL — many readers + 1 writer) ──────────────
# Tuned for 20 concurrent users. WAL allows concurrent reads; writes queue
# via busy_timeout. Pool reuses connections to skip open/pragma overhead.
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "32"))
_pool: "queue.Queue[sqlite3.Connection]" = queue.Queue(maxsize=_POOL_SIZE)
_pool_lock = threading.Lock()
_pool_created = 0


class _PooledConn(sqlite3.Connection):
    """sqlite3.Connection subclass — .close() returns to pool."""
    def close(self):  # type: ignore[override]
        try:
            if self.in_transaction:
                self.rollback()
        except Exception:
            pass
        try:
            _pool.put_nowait(self)
        except queue.Full:
            super().close()

    def _real_close(self):
        super().close()


def _build_conn() -> sqlite3.Connection:
    # Default deferred isolation — c.commit() works as code expects.
    c = sqlite3.connect(
        DB_PATH, check_same_thread=False, timeout=30, factory=_PooledConn,
    )
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA synchronous=NORMAL")        # WAL-safe; faster than FULL
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("PRAGMA cache_size=-20000")         # ~20 MB page cache
    c.execute("PRAGMA wal_autocheckpoint=1000")
    return c


def _conn() -> sqlite3.Connection:
    """Return pooled connection. Call .close() to return to pool."""
    global _pool_created
    try:
        return _pool.get_nowait()
    except queue.Empty:
        pass
    with _pool_lock:
        if _pool_created < _POOL_SIZE:
            c = _build_conn()
            _pool_created += 1
            return c
    return _pool.get(timeout=10)


@atexit.register
def _drain_pool():
    while True:
        try:
            c = _pool.get_nowait()
            try:
                c._real_close()  # type: ignore[attr-defined]
            except Exception:
                pass
        except queue.Empty:
            break


@contextmanager
def db():
    """Context manager wrapping _conn() — auto-closes."""
    c = _conn()
    try:
        yield c
    finally:
        c.close()


def _add_column(c, table: str, col_def: str):
    """Idempotently add a column to a table (no-op if it already exists)."""
    col_name = col_def.split()[0]
    try:
        existing = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return
    if col_name in existing:
        return
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        c.commit()
    except sqlite3.OperationalError:
        pass


def _migrate_columns(c):
    """Idempotent ALTER TABLE for added columns. Each in its own try/except."""
    contact_cols = [
        "wechat_id TEXT",
        "wechat_qr_url TEXT",
        "whatsapp TEXT",
        "viber TEXT",
        "telegram TEXT",
        "line_id TEXT",
        "signal_phone TEXT",
        "messengers TEXT",
        "phone_e164 TEXT",
    ]
    for col_def in contact_cols:
        try:
            c.execute(f"ALTER TABLE contacts ADD COLUMN {col_def}")
            c.commit()
        except sqlite3.OperationalError:
            pass

    doc_cols = [
        "catalog_url TEXT",
        "qr_payloads TEXT",
        "source_channel TEXT",
        "source_sender TEXT",
        "file_hash TEXT",
    ]
    for col_def in doc_cols:
        try:
            c.execute(f"ALTER TABLE documents ADD COLUMN {col_def}")
            c.commit()
        except sqlite3.OperationalError:
            pass

    # ── Expanded EXIF / geocode / quality / client metadata columns ──
    expanded_doc_cols = [
        "gps_altitude REAL",
        "gps_heading REAL",
        "gps_speed REAL",
        "gps_source TEXT",
        "gps_accuracy REAL",
        "country TEXT",
        "city TEXT",
        "address_full TEXT",
        "lens_model TEXT",
        "focal_length REAL",
        "f_number REAL",
        "iso INTEGER",
        "exposure_time TEXT",
        "software TEXT",
        "sub_sec_time TEXT",
        "client_timezone TEXT",
        "client_user_agent TEXT",
        "client_ip TEXT",
        "client_timestamp TEXT",
        "image_phash TEXT",
        "blur_score REAL",
        "is_blurry INTEGER DEFAULT 0",
        "near_dup_of TEXT",
    ]
    for col_def in expanded_doc_cols:
        _add_column(c, "documents", col_def)

    _add_column(c, "documents", "device_signals TEXT")  # JSON blob

    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_docs_country ON documents(country)",
        "CREATE INDEX IF NOT EXISTS idx_docs_city ON documents(city)",
        "CREATE INDEX IF NOT EXISTS idx_docs_phash ON documents(image_phash)",
        "CREATE INDEX IF NOT EXISTS idx_docs_blur ON documents(is_blurry)",
    ):
        try:
            c.execute(idx_sql)
            c.commit()
        except sqlite3.OperationalError:
            pass

    # ── Tenancy / ownership columns ───────────────────────────────
    _add_column(c, "documents", "owner_uuid TEXT")
    _add_column(c, "documents", "is_shared INTEGER DEFAULT 0")
    _add_column(c, "contacts", "owner_uuid TEXT")
    _add_column(c, "contacts", "is_shared INTEGER DEFAULT 0")
    _add_column(c, "products", "owner_uuid TEXT")
    _add_column(c, "products", "is_shared INTEGER DEFAULT 0")
    _add_column(c, "queue", "owner_uuid TEXT")

    # Indexes
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_phone_e164 ON contacts(phone_e164)")
        c.commit()
    except sqlite3.OperationalError:
        pass
    try:
        # Dedup is handled via near_dup_of + image_phash; a UNIQUE here
        # collides with INSERT OR REPLACE and breaks FKs to products/contacts.
        c.execute("DROP INDEX IF EXISTS idx_doc_filehash")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_filehash ON documents(file_hash) WHERE file_hash IS NOT NULL"
        )
        c.commit()
    except sqlite3.OperationalError:
        pass

    # Tenancy indexes
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_docs_owner ON documents(owner_uuid)",
        "CREATE INDEX IF NOT EXISTS idx_docs_shared ON documents(is_shared)",
        "CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts(owner_uuid)",
        "CREATE INDEX IF NOT EXISTS idx_products_owner ON products(owner_uuid)",
    ):
        try:
            c.execute(idx_sql)
            c.commit()
        except sqlite3.OperationalError:
            pass

    # ── Audit columns (updated_at, source_channel, edit_count, owner_name) ──
    _add_column(c, "documents", "updated_at TEXT")
    _add_column(c, "documents", "source_channel TEXT DEFAULT 'upload'")
    _add_column(c, "documents", "edit_count INTEGER DEFAULT 0")

    _add_column(c, "contacts", "updated_at TEXT")
    _add_column(c, "contacts", "source_channel TEXT DEFAULT 'upload'")
    _add_column(c, "contacts", "edit_count INTEGER DEFAULT 0")
    _add_column(c, "contacts", "owner_name TEXT")
    _add_column(c, "contacts", "backfill_source TEXT")
    _add_column(c, "documents", "quality_score REAL")
    _add_column(c, "documents", "needs_revision INTEGER DEFAULT 0")
    # cron_config — admin-editable job schedules
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cron_config (
            job_id TEXT PRIMARY KEY,
            cron_hour INTEGER,                -- 0-23 or NULL for interval-based
            cron_minute INTEGER DEFAULT 0,
            interval_hours INTEGER,           -- alt: interval-based job
            enabled INTEGER DEFAULT 1,
            updated_at TEXT,
            updated_by TEXT
        );
    """)
    # Seed defaults (idempotent)
    _seed_defaults = [
        ("vs_prune",        None,  0,    24, 1),   # every 24h
        ("backfill_cheap",  2,     0,    None, 1),
        ("dedup_scan",      4,     0,    None, 1),
        ("ts_summary",      5,     0,    None, 1),
        ("backfill_llm",    None,  0,    None, 0), # disabled by default
    ]
    for jid, hh, mm, iv, en in _seed_defaults:
        c.execute(
            "INSERT OR IGNORE INTO cron_config "
            "(job_id, cron_hour, cron_minute, interval_hours, enabled, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (jid, hh, mm, iv, en, _now_iso()),
        )

    # llm_usage table — track tokens + cost per call
    c.executescript("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            user_uuid TEXT,
            op TEXT NOT NULL,           -- 'extract' | 'chat' | 'categorize' | 'backfill'
            model TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_llm_ts ON llm_usage(ts);
        CREATE INDEX IF NOT EXISTS idx_llm_user ON llm_usage(user_uuid, ts);
        CREATE INDEX IF NOT EXISTS idx_llm_op ON llm_usage(op, ts);
    """)

    _add_column(c, "products", "updated_at TEXT")
    _add_column(c, "products", "source_channel TEXT DEFAULT 'upload'")
    _add_column(c, "products", "edit_count INTEGER DEFAULT 0")

    # Trade-show grouping
    _add_column(c, "documents", "trade_show TEXT")
    _add_column(c, "queue", "trade_show TEXT")
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_docs_trade_show ON documents(trade_show)")
        c.commit()
    except sqlite3.OperationalError:
        pass

    # Currency separation on products
    _add_column(c, "products", "currency TEXT")
    _add_column(c, "products", "price_amount REAL")

    _add_column(c, "queue", "updated_at TEXT")
    _add_column(c, "queue", "source_channel TEXT DEFAULT 'upload'")

    # chat_history: scope to user
    _add_column(c, "chat_history", "user_uuid TEXT")
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_uuid)")
        c.commit()
    except sqlite3.OperationalError:
        pass


# ---------------------------------------------------------------------------
# Tenancy helpers
# ---------------------------------------------------------------------------
def visibility_clause(table_alias, user):
    """Returns (sql_fragment, params) gating rows by ownership.
    Strict per-user. super_admin and admin see all. Users see ONLY own."""
    if not user:
        return ("", [])
    if user.get("role") in ("super_admin", "admin"):
        return ("", [])
    a = f"{table_alias}." if table_alias else ""
    return (f"{a}owner_uuid = ?", [user["uuid"]])


def can_edit(row: dict, user: dict) -> bool:
    """User may edit row if they own it OR are admin/super_admin."""
    if not user:
        return False
    if user.get("role") in ("super_admin", "admin"):
        return True
    return bool(row) and row.get("owner_uuid") == user.get("uuid")


def backfill_ownership(c):
    """One-time backfill: legacy rows get assigned to super_admin and marked shared."""
    try:
        cnt = c.execute("SELECT COUNT(*) FROM documents WHERE owner_uuid IS NULL").fetchone()[0]
    except sqlite3.OperationalError:
        return
    if cnt == 0:
        return
    try:
        admin = c.execute("SELECT uuid FROM users WHERE role='super_admin' LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return
    if not admin:
        return
    uid = admin["uuid"]
    # legacy rows now private to super_admin under strict mode
    c.execute("UPDATE documents SET owner_uuid=?, is_shared=0 WHERE owner_uuid IS NULL", (uid,))
    c.execute("UPDATE contacts SET owner_uuid=?, is_shared=0 WHERE owner_uuid IS NULL", (uid,))
    c.execute("UPDATE products SET owner_uuid=?, is_shared=0 WHERE owner_uuid IS NULL", (uid,))
    c.execute("UPDATE queue SET owner_uuid=? WHERE owner_uuid IS NULL", (uid,))
    # Backfill chat_history user_uuid for any NULL → super_admin
    try:
        c.execute("UPDATE chat_history SET user_uuid=? WHERE user_uuid IS NULL", (uid,))
    except sqlite3.OperationalError:
        pass
    c.commit()
    print(f"[tenancy] backfilled {cnt} legacy rows to super_admin (private under strict mode)")


def run_tenancy_backfill():
    """Public entry point — call after users table + super_admin exist."""
    c = _conn()
    try:
        backfill_ownership(c)
        backfill_aux_tables(c)
    finally:
        c.close()


def init_db():
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_path TEXT,
            image_type TEXT,
            company TEXT,
            title TEXT,
            products TEXT,
            contact TEXT,
            key_info TEXT,
            raw_text TEXT,
            full_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(folder, source_file)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            folder, source_file, company, title, raw_text, key_info,
            content='documents',
            content_rowid='id'
        );
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, folder, source_file, company, title, raw_text, key_info)
            VALUES (new.id, new.folder, new.source_file, new.company, new.title, new.raw_text, new.key_info);
        END;
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, folder, source_file, company, title, raw_text, key_info)
            VALUES ('delete', old.id, old.folder, old.source_file, old.company, old.title, old.raw_text, old.key_info);
        END;
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            image_type TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            document_uuid TEXT,
            document_id INTEGER,
            folder TEXT,
            source_file TEXT,
            company TEXT,
            name TEXT,
            model TEXT,
            specs TEXT,
            category TEXT,
            price TEXT,
            image_desc TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            document_uuid TEXT,
            document_id INTEGER,
            folder TEXT,
            source_file TEXT,
            company TEXT,
            person TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        );
        CREATE TABLE IF NOT EXISTS wechat_chat_map (
            chat_hash TEXT PRIMARY KEY,
            vendor_company TEXT,
            contact_uuid TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    _migrate_columns(c)

    # Add uuid column to documents if not exists (SQLite has no IF NOT EXISTS for ALTER)
    try:
        c.execute("ALTER TABLE documents ADD COLUMN uuid TEXT")
        c.commit()
    except Exception:
        pass  # Column already exists

    # Add metadata column to documents if not exists
    try:
        c.execute("ALTER TABLE documents ADD COLUMN metadata TEXT")
        c.commit()
    except Exception:
        pass  # Column already exists

    # Add flat metadata columns for SQL queryability
    for col_def in [
        "gps_lat REAL",
        "gps_lng REAL",
        "date_taken TEXT",
        "camera_make TEXT",
        "camera_model TEXT",
        "img_width INTEGER",
        "img_height INTEGER",
        "file_size_kb REAL",
    ]:
        try:
            c.execute(f"ALTER TABLE documents ADD COLUMN {col_def}")
            c.commit()
        except Exception:
            pass  # Column already exists

    _migrate_auth_tables(c)
    _migrate_aux_tables(c)
    _migrate_merge_tables(c)

    c.close()


def _migrate_aux_tables(c):
    """Create tags, document_tags, notes, meetings, events tables (idempotent)."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            name TEXT UNIQUE NOT NULL,
            color TEXT DEFAULT '#C96442',
            created_at TEXT NOT NULL,
            created_by TEXT
        );

        CREATE TABLE IF NOT EXISTS document_tags (
            document_uuid TEXT NOT NULL,
            tag_uuid TEXT NOT NULL,
            added_at TEXT NOT NULL,
            added_by TEXT,
            PRIMARY KEY (document_uuid, tag_uuid)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            entity_type TEXT NOT NULL,
            entity_uuid TEXT NOT NULL,
            body TEXT NOT NULL,
            owner_uuid TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_uuid);
        CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes(owner_uuid);

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            contact_uuid TEXT,
            company TEXT,
            person TEXT,
            meeting_date TEXT NOT NULL,
            location TEXT,
            city TEXT,
            notes TEXT,
            outcome TEXT,
            owner_uuid TEXT NOT NULL,
            is_shared INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_meetings_contact ON meetings(contact_uuid);
        CREATE INDEX IF NOT EXISTS idx_meetings_owner ON meetings(owner_uuid);
        CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(meeting_date);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_type TEXT NOT NULL,
            entity_type TEXT,
            entity_uuid TEXT,
            user_uuid TEXT,
            detail_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_uuid);
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
    """)
    c.commit()


# ---------------------------------------------------------------------------
# Aux helpers: tags, document_tags, notes, meetings, events
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Tags ────────────────────────────────────────────────────────────
def create_tag(c, name: str, color: str = None, user_uuid: str = None) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("tag name required")
    existing = c.execute("SELECT uuid FROM tags WHERE name = ?", (name,)).fetchone()
    if existing:
        return existing["uuid"]
    new_uuid = str(uuid4())
    c.execute(
        "INSERT INTO tags (uuid, name, color, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
        (new_uuid, name, color or "#C96442", _now_iso(), user_uuid),
    )
    c.commit()
    return new_uuid


def list_tags(c, user=None):
    rows = c.execute("SELECT * FROM tags ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def delete_tag(c, tag_uuid: str) -> int:
    n = c.execute("DELETE FROM tags WHERE uuid = ?", (tag_uuid,)).rowcount
    c.execute("DELETE FROM document_tags WHERE tag_uuid = ?", (tag_uuid,))
    c.commit()
    return n


def get_tag(c, tag_uuid: str):
    row = c.execute("SELECT * FROM tags WHERE uuid = ?", (tag_uuid,)).fetchone()
    return dict(row) if row else None


def tag_document(c, doc_uuid: str, tag_uuid: str, user_uuid: str = None) -> int:
    try:
        c.execute(
            "INSERT INTO document_tags (document_uuid, tag_uuid, added_at, added_by) VALUES (?, ?, ?, ?)",
            (doc_uuid, tag_uuid, _now_iso(), user_uuid),
        )
        c.commit()
        return 1
    except sqlite3.IntegrityError:
        return 0


def untag_document(c, doc_uuid: str, tag_uuid: str) -> int:
    n = c.execute(
        "DELETE FROM document_tags WHERE document_uuid = ? AND tag_uuid = ?",
        (doc_uuid, tag_uuid),
    ).rowcount
    c.commit()
    return n


def list_doc_tags(c, doc_uuid: str):
    rows = c.execute(
        "SELECT t.uuid, t.name, t.color FROM tags t "
        "JOIN document_tags dt ON dt.tag_uuid = t.uuid WHERE dt.document_uuid = ? "
        "ORDER BY t.name",
        (doc_uuid,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Notes ───────────────────────────────────────────────────────────
def create_note(c, entity_type: str, entity_uuid: str, body: str, owner_uuid: str) -> str:
    new_uuid = str(uuid4())
    c.execute(
        "INSERT INTO notes (uuid, entity_type, entity_uuid, body, owner_uuid, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_uuid, entity_type, entity_uuid, body, owner_uuid, _now_iso()),
    )
    c.commit()
    return new_uuid


def list_notes(c, entity_type: str, entity_uuid: str, user=None):
    rows = c.execute(
        "SELECT * FROM notes WHERE entity_type = ? AND entity_uuid = ? ORDER BY created_at DESC",
        (entity_type, entity_uuid),
    ).fetchall()
    out = [dict(r) for r in rows]
    if not user or user.get("role") in ("super_admin", "admin"):
        return out
    uid = user["uuid"]
    return [n for n in out if n.get("owner_uuid") == uid]


def get_note(c, note_uuid: str):
    row = c.execute("SELECT * FROM notes WHERE uuid = ?", (note_uuid,)).fetchone()
    return dict(row) if row else None


def update_note(c, note_uuid: str, body: str, user_uuid: str) -> int:
    row = c.execute("SELECT owner_uuid FROM notes WHERE uuid = ?", (note_uuid,)).fetchone()
    if not row:
        return 0
    if row["owner_uuid"] != user_uuid:
        return -1  # forbidden sentinel
    n = c.execute(
        "UPDATE notes SET body = ?, updated_at = ? WHERE uuid = ?",
        (body, _now_iso(), note_uuid),
    ).rowcount
    c.commit()
    return n


def delete_note(c, note_uuid: str, user_uuid: str, is_admin: bool = False) -> int:
    row = c.execute("SELECT owner_uuid FROM notes WHERE uuid = ?", (note_uuid,)).fetchone()
    if not row:
        return 0
    if not is_admin and row["owner_uuid"] != user_uuid:
        return -1
    n = c.execute("DELETE FROM notes WHERE uuid = ?", (note_uuid,)).rowcount
    c.commit()
    return n


# ── Meetings ────────────────────────────────────────────────────────
_MEETING_UPDATABLE = {"contact_uuid", "company", "person", "meeting_date",
                      "location", "city", "notes", "outcome", "is_shared"}


def create_meeting(c, owner_uuid: str, **fields) -> str:
    new_uuid = str(uuid4())
    contact_uuid = fields.get("contact_uuid")
    company = fields.get("company")
    person = fields.get("person")
    meeting_date = fields.get("meeting_date") or _now_iso()
    location = fields.get("location")
    city = fields.get("city")
    notes = fields.get("notes")
    outcome = fields.get("outcome")
    is_shared = int(bool(fields.get("is_shared")))
    c.execute(
        "INSERT INTO meetings (uuid, contact_uuid, company, person, meeting_date, "
        "location, city, notes, outcome, owner_uuid, is_shared, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_uuid, contact_uuid, company, person, meeting_date,
         location, city, notes, outcome, owner_uuid, is_shared, _now_iso()),
    )
    c.commit()
    return new_uuid


def list_meetings(c, user=None, contact_uuid: str = None):
    where = []
    params = []
    if contact_uuid:
        where.append("contact_uuid = ?")
        params.append(contact_uuid)
    vc, vp = visibility_clause("", user)
    if vc:
        where.append(vc)
        params.extend(vp)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = c.execute(
        f"SELECT * FROM meetings {where_sql} ORDER BY meeting_date DESC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_meeting(c, meeting_uuid: str):
    row = c.execute("SELECT * FROM meetings WHERE uuid = ?", (meeting_uuid,)).fetchone()
    return dict(row) if row else None


def update_meeting(c, meeting_uuid: str, fields: dict, user_uuid: str, is_admin: bool = False) -> int:
    row = c.execute("SELECT owner_uuid FROM meetings WHERE uuid = ?", (meeting_uuid,)).fetchone()
    if not row:
        return 0
    if not is_admin and row["owner_uuid"] != user_uuid:
        return -1
    sets = {k: v for k, v in (fields or {}).items() if k in _MEETING_UPDATABLE}
    if not sets:
        return 0
    if "is_shared" in sets:
        sets["is_shared"] = int(bool(sets["is_shared"]))
    cols = ", ".join(f"{k} = ?" for k in sets)
    params = list(sets.values()) + [meeting_uuid]
    n = c.execute(f"UPDATE meetings SET {cols} WHERE uuid = ?", params).rowcount
    c.commit()
    return n


def delete_meeting(c, meeting_uuid: str, user_uuid: str, is_admin: bool = False) -> int:
    row = c.execute("SELECT owner_uuid FROM meetings WHERE uuid = ?", (meeting_uuid,)).fetchone()
    if not row:
        return 0
    if not is_admin and row["owner_uuid"] != user_uuid:
        return -1
    n = c.execute("DELETE FROM meetings WHERE uuid = ?", (meeting_uuid,)).rowcount
    c.commit()
    return n


# ── Events / audit ──────────────────────────────────────────────────
def log_event(c, event_type: str, entity_type: str = None, entity_uuid: str = None,
              user_uuid: str = None, detail: dict = None):
    """Best-effort audit log insert. Never raise."""
    try:
        detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
        c.execute(
            "INSERT INTO events (ts, event_type, entity_type, entity_uuid, user_uuid, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_now_iso(), event_type, entity_type, entity_uuid, user_uuid, detail_json),
        )
        c.commit()
    except Exception:
        pass


def log_event_safe(event_type: str, entity_type: str = None, entity_uuid: str = None,
                   user_uuid: str = None, detail: dict = None):
    """Convenience: open own connection, log, close. Never raise."""
    try:
        conn = _conn()
        try:
            log_event(conn, event_type, entity_type, entity_uuid, user_uuid, detail)
        finally:
            conn.close()
    except Exception:
        pass


# LLM cost rates per 1M tokens. Update as OpenRouter pricing shifts.
LLM_PRICING_USD_PER_M = {
    # input, output
    "google/gemini-3.1-flash-lite-preview": (0.075, 0.30),
    "openai/text-embedding-3-small":        (0.02,  0.0),
    "default":                              (0.30,  1.20),
}


def cron_config_list() -> list[dict]:
    c = _conn()
    try:
        rows = c.execute("SELECT * FROM cron_config ORDER BY job_id").fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def cron_config_get(job_id: str) -> dict | None:
    c = _conn()
    try:
        row = c.execute("SELECT * FROM cron_config WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def cron_config_update(job_id: str, *, cron_hour=None, cron_minute=None,
                       interval_hours=None, enabled=None, updated_by: str = None) -> dict:
    c = _conn()
    try:
        cur = c.execute("SELECT * FROM cron_config WHERE job_id = ?", (job_id,)).fetchone()
        if not cur:
            raise ValueError(f"unknown job_id {job_id}")
        updates = {}
        if cron_hour is not None:     updates["cron_hour"] = int(cron_hour) if cron_hour != "" else None
        if cron_minute is not None:   updates["cron_minute"] = int(cron_minute)
        if interval_hours is not None: updates["interval_hours"] = int(interval_hours) if interval_hours != "" else None
        if enabled is not None:       updates["enabled"] = int(bool(enabled))
        if not updates:
            return dict(cur)
        sets = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [_now_iso(), updated_by, job_id]
        c.execute(
            f"UPDATE cron_config SET {sets}, updated_at = ?, updated_by = ? WHERE job_id = ?",
            params,
        )
        c.commit()
        row = c.execute("SELECT * FROM cron_config WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        c.close()


def log_llm_usage(user_uuid: str, op: str, model: str,
                  prompt_tokens: int = 0, completion_tokens: int = 0):
    """Best-effort log. Never raises."""
    try:
        prompt_tokens = int(prompt_tokens or 0)
        completion_tokens = int(completion_tokens or 0)
        total = prompt_tokens + completion_tokens
        rates = LLM_PRICING_USD_PER_M.get(model) or LLM_PRICING_USD_PER_M["default"]
        cost = (prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1_000_000
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO llm_usage "
                "(ts, user_uuid, op, model, prompt_tokens, completion_tokens, total_tokens, cost_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now_iso(), user_uuid, op, model, prompt_tokens, completion_tokens, total, cost),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def llm_cost_summary(days: int = 30, user_uuid: str = None) -> dict:
    """Aggregate cost + tokens over period, grouped by day + op + user."""
    conn = _conn()
    try:
        params: list = []
        where = "WHERE ts >= datetime('now', ?)"
        params.append(f"-{int(days)} day")
        if user_uuid:
            where += " AND user_uuid = ?"
            params.append(user_uuid)
        by_day = conn.execute(
            f"SELECT date(ts) AS day, SUM(total_tokens) AS tokens, SUM(cost_usd) AS cost, COUNT(*) AS calls "
            f"FROM llm_usage {where} GROUP BY date(ts) ORDER BY day DESC",
            params,
        ).fetchall()
        by_op = conn.execute(
            f"SELECT op, SUM(total_tokens) AS tokens, SUM(cost_usd) AS cost, COUNT(*) AS calls "
            f"FROM llm_usage {where} GROUP BY op ORDER BY cost DESC",
            params,
        ).fetchall()
        by_user = conn.execute(
            f"SELECT COALESCE(u.name, 'unknown') AS name, l.user_uuid, "
            f"SUM(l.total_tokens) AS tokens, SUM(l.cost_usd) AS cost, COUNT(*) AS calls "
            f"FROM llm_usage l LEFT JOIN users u ON u.uuid = l.user_uuid {where.replace('ts', 'l.ts')} "
            f"GROUP BY l.user_uuid ORDER BY cost DESC LIMIT 50",
            params,
        ).fetchall()
        totals = conn.execute(
            f"SELECT SUM(total_tokens) AS tokens, SUM(cost_usd) AS cost, COUNT(*) AS calls "
            f"FROM llm_usage {where}",
            params,
        ).fetchone()
        return {
            "days": days,
            "totals": dict(totals) if totals else {"tokens": 0, "cost": 0, "calls": 0},
            "by_day": [dict(r) for r in by_day],
            "by_op": [dict(r) for r in by_op],
            "by_user": [dict(r) for r in by_user],
        }
    finally:
        conn.close()


def trade_show_summary(trade_show: str, user_uuid: str = None) -> dict:
    """Build summary for a trade show — counts, top companies, contacts."""
    if not trade_show:
        return {}
    conn = _conn()
    try:
        scope = ""
        params: list = [trade_show]
        if user_uuid:
            scope = " AND owner_uuid = ?"
            params.append(user_uuid)
        totals_row = conn.execute(
            f"SELECT COUNT(*) AS docs, COUNT(DISTINCT company) AS companies, "
            f"MIN(created_at) AS first_seen, MAX(created_at) AS last_seen "
            f"FROM documents WHERE trade_show = ?{scope}",
            params,
        ).fetchone()
        top_companies = conn.execute(
            f"SELECT company, COUNT(*) AS n FROM documents "
            f"WHERE trade_show = ?{scope} AND company IS NOT NULL AND TRIM(company) != '' "
            f"GROUP BY company ORDER BY n DESC LIMIT 10",
            params,
        ).fetchall()
        contacts = conn.execute(
            f"SELECT c.company, c.person, c.phone, c.email "
            f"FROM contacts c JOIN documents d ON c.document_uuid = d.uuid "
            f"WHERE d.trade_show = ?{scope} LIMIT 100",
            params,
        ).fetchall()
        product_count = conn.execute(
            f"SELECT COUNT(*) FROM products p JOIN documents d ON p.document_uuid = d.uuid "
            f"WHERE d.trade_show = ?{scope}",
            params,
        ).fetchone()[0]
        meetings_count = conn.execute(
            f"SELECT COUNT(*) FROM meetings WHERE company IN "
            f"(SELECT DISTINCT company FROM documents WHERE trade_show = ?{scope})",
            params,
        ).fetchone()[0]
        return {
            "trade_show": trade_show,
            "totals": dict(totals_row) if totals_row else {},
            "products": product_count,
            "meetings": meetings_count,
            "top_companies": [dict(r) for r in top_companies],
            "contacts_sample": [dict(r) for r in contacts[:20]],
            "contact_count": len(contacts),
        }
    finally:
        conn.close()


def usage_heatmap(days: int = 14, user_uuid: str = None) -> dict:
    """Upload count by (day, hour) buckets."""
    conn = _conn()
    try:
        params: list = [f"-{int(days)} day"]
        where = "WHERE created_at >= datetime('now', ?)"
        if user_uuid:
            where += " AND owner_uuid = ?"
            params.append(user_uuid)
        rows = conn.execute(
            f"SELECT strftime('%Y-%m-%d', created_at) AS day, "
            f"strftime('%H', created_at) AS hour, COUNT(*) AS n "
            f"FROM documents {where} GROUP BY day, hour ORDER BY day, hour",
            params,
        ).fetchall()
        return {"days": days, "cells": [dict(r) for r in rows]}
    finally:
        conn.close()


def conversion_funnel(days: int = 30, user_uuid: str = None) -> dict:
    """Counts: uploaded → extracted → contact_saved → meeting_created."""
    conn = _conn()
    try:
        params: list = [f"-{int(days)} day"]
        scope = ""
        if user_uuid:
            scope = " AND owner_uuid = ?"
            params2 = params + [user_uuid]
        else:
            params2 = params
        uploaded = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE created_at >= datetime('now', ?)" + scope,
            params2,
        ).fetchone()[0]
        extracted = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE created_at >= datetime('now', ?)" + scope,
            params2,
        ).fetchone()[0]
        if user_uuid:
            ct_scope = " AND owner_uuid = ?"
        else:
            ct_scope = ""
        contacts_saved = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE created_at >= datetime('now', ?)" + ct_scope,
            params2 if user_uuid else params,
        ).fetchone()[0]
        meetings = conn.execute(
            "SELECT COUNT(*) FROM meetings WHERE created_at >= datetime('now', ?)" + (
                " AND owner_uuid = ?" if user_uuid else ""
            ),
            params2 if user_uuid else params,
        ).fetchone()[0]
        return {
            "days": days,
            "uploaded": uploaded,
            "extracted": extracted,
            "contacts_saved": contacts_saved,
            "meetings_created": meetings,
        }
    finally:
        conn.close()


def list_events(c, limit: int = 100, user_uuid: str = None, event_type: str = None,
                requester=None):
    where = []
    params = []
    # non-admin can only see own events
    if requester and requester.get("role") not in ("super_admin", "admin"):
        where.append("user_uuid = ?")
        params.append(requester["uuid"])
    else:
        if user_uuid:
            where.append("user_uuid = ?")
            params.append(user_uuid)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = c.execute(
        f"SELECT * FROM events {where_sql} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def backfill_aux_tables(c=None):
    """No-op currently — tables created empty. Just log."""
    print("[aux] notes/meetings/tags/events tables ready")


def _migrate_merge_tables(c):
    """Create merge_proposals + merge_blacklist for human-approved dedup."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS merge_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            entity_type TEXT NOT NULL,       -- 'contact' | 'document'
            keep_uuid TEXT NOT NULL,
            drop_uuid TEXT NOT NULL,
            match_reason TEXT NOT NULL,      -- phone_e164|email|company_person|file_hash|phash|filename
            confidence REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',   -- pending|approved|rejected|undone
            proposed_by TEXT DEFAULT 'auto_cron',
            reviewed_by TEXT,
            reviewed_at TEXT,
            before_snapshot TEXT,            -- JSON of drop row pre-merge
            after_snapshot TEXT,             -- JSON post-merge (for undo)
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mp_status ON merge_proposals(status);
        CREATE INDEX IF NOT EXISTS idx_mp_entity ON merge_proposals(entity_type, status);
        CREATE INDEX IF NOT EXISTS idx_mp_pair ON merge_proposals(keep_uuid, drop_uuid);

        CREATE TABLE IF NOT EXISTS merge_blacklist (
            uuid_a TEXT NOT NULL,
            uuid_b TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (uuid_a, uuid_b)
        );
    """)


def merge_proposal_create(entity_type: str, keep_uuid: str, drop_uuid: str,
                          match_reason: str, confidence: float,
                          before_snapshot: dict,
                          proposed_by: str = "auto_cron") -> str | None:
    """Insert proposal. Returns proposal uuid, or None if blacklisted/duplicate."""
    from uuid import uuid4 as _uuid4
    import json as _json
    a, b = sorted([keep_uuid, drop_uuid])
    c = _conn()
    try:
        bl = c.execute(
            "SELECT 1 FROM merge_blacklist WHERE uuid_a = ? AND uuid_b = ?",
            (a, b),
        ).fetchone()
        if bl:
            return None
        # Skip if pending or approved already exists for same pair
        dup = c.execute(
            "SELECT uuid FROM merge_proposals "
            "WHERE entity_type = ? AND status IN ('pending', 'approved') "
            "AND ((keep_uuid = ? AND drop_uuid = ?) OR (keep_uuid = ? AND drop_uuid = ?))",
            (entity_type, keep_uuid, drop_uuid, drop_uuid, keep_uuid),
        ).fetchone()
        if dup:
            return None
        proposal_uuid = str(_uuid4())
        c.execute(
            """
            INSERT INTO merge_proposals
            (uuid, entity_type, keep_uuid, drop_uuid, match_reason, confidence,
             status, proposed_by, before_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (proposal_uuid, entity_type, keep_uuid, drop_uuid, match_reason,
             float(confidence), proposed_by,
             _json.dumps(before_snapshot, ensure_ascii=False, default=str),
             _now_iso()),
        )
        c.commit()
        return proposal_uuid
    finally:
        c.close()


def _enrich_doc_preview(d: dict, c) -> dict:
    """Add summary fields (products_count, contact_summary, raw_text_snippet)."""
    # Parse JSON columns
    products = d.get("products")
    if isinstance(products, str):
        try: products = json.loads(products)
        except Exception: products = []
    if not isinstance(products, list): products = []
    d["products_count"] = len(products)
    d["products_summary"] = [
        (p.get("name") or p.get("product_name") or "")
        for p in products[:5] if isinstance(p, dict)
    ]
    contact = d.get("contact")
    if isinstance(contact, str):
        try: contact = json.loads(contact)
        except Exception: contact = {}
    if not isinstance(contact, dict): contact = {}
    d["contact_summary"] = {
        "person": contact.get("person") or "",
        "phone":  contact.get("phone") or contact.get("phone_e164") or "",
        "email":  contact.get("email") or "",
    }
    raw = (d.get("raw_text") or "").strip()
    d["raw_text_snippet"] = raw[:160] + ("…" if len(raw) > 160 else "")
    d["has_gps"] = bool(d.get("gps_lat"))
    # Drop bulky raw_text/products/contact JSON from response (we kept summaries)
    d.pop("raw_text", None)
    d.pop("products", None)
    d.pop("contact", None)
    return d


def merge_proposal_clusters(status: str = "pending", entity_type: str | None = None,
                            min_confidence: float = 0.0, limit: int = 100) -> list[dict]:
    """Group pending proposals by keep_uuid + match_reason.

    Returns list of clusters:
      {keep_uuid, match_reason, entity_type, confidence_avg, drop_count,
       keep_preview: dict, drops: [{uuid, snapshot_preview, proposal_uuid}, …]}

    UI shows one card per cluster → single "merge all" button.
    """
    c = _conn()
    try:
        where = ["status = ?", "confidence >= ?"]
        params: list = [status, min_confidence]
        if entity_type:
            where.append("entity_type = ?")
            params.append(entity_type)
        rows = c.execute(
            f"SELECT * FROM merge_proposals WHERE {' AND '.join(where)} "
            f"ORDER BY confidence DESC, created_at DESC",
            params,
        ).fetchall()

        # Group by (keep_uuid, match_reason)
        groups: dict[tuple, dict] = {}
        for r in rows:
            key = (r["keep_uuid"], r["match_reason"])
            if key not in groups:
                groups[key] = {
                    "keep_uuid": r["keep_uuid"],
                    "match_reason": r["match_reason"],
                    "entity_type": r["entity_type"],
                    "confidences": [],
                    "drops": [],
                    "proposal_uuids": [],
                }
            g = groups[key]
            g["confidences"].append(r["confidence"])
            g["proposal_uuids"].append(r["uuid"])
            try:
                snap = json.loads(r["before_snapshot"]) if r["before_snapshot"] else {}
            except Exception:
                snap = {}
            if r["entity_type"] == "document" and isinstance(snap, dict):
                try:
                    snap = _enrich_doc_preview(snap, None)
                except Exception:
                    pass
            g["drops"].append({
                "proposal_uuid": r["uuid"],
                "drop_uuid": r["drop_uuid"],
                "snapshot": snap,
            })

        # Fetch keep previews
        out = []
        for (keep_uuid, reason), g in groups.items():
            ent = g["entity_type"]
            keep_preview = {}
            if ent == "document":
                row = c.execute(
                    "SELECT uuid, folder, source_file, company, title, image_type, "
                    "image_phash, file_hash, trade_show, file_size_kb, created_at, "
                    "raw_text, products, contact, gps_lat, gps_lng, country, city, "
                    "quality_score, needs_revision, date_taken, camera_make, owner_uuid "
                    "FROM documents WHERE uuid = ?", (keep_uuid,)
                ).fetchone()
                if row:
                    keep_preview = dict(row)
                    keep_preview = _enrich_doc_preview(keep_preview, c)
            elif ent == "contact":
                row = c.execute(
                    "SELECT uuid, company, person, phone, phone_e164, email, website, address, "
                    "messengers, owner_name, created_at, document_uuid, source_channel, edit_count "
                    "FROM contacts WHERE uuid = ?", (keep_uuid,)
                ).fetchone()
                if row:
                    keep_preview = dict(row)
            confs = g["confidences"]
            avg_conf = sum(confs) / max(len(confs), 1)
            out.append({
                "keep_uuid": keep_uuid,
                "match_reason": reason,
                "entity_type": ent,
                "confidence": round(avg_conf, 3),
                "drop_count": len(g["drops"]),
                "keep_preview": keep_preview,
                "drops": g["drops"],
                "proposal_uuids": g["proposal_uuids"],
            })

        # Sort: biggest cluster first, then highest confidence
        out.sort(key=lambda x: (-x["drop_count"], -x["confidence"]))
        return out[:limit]
    finally:
        c.close()


def merge_proposal_list(status: str = "pending", entity_type: str | None = None,
                        min_confidence: float = 0.0, limit: int = 500) -> list[dict]:
    c = _conn()
    try:
        where = ["status = ?", "confidence >= ?"]
        params: list = [status, min_confidence]
        if entity_type:
            where.append("entity_type = ?")
            params.append(entity_type)
        params.append(limit)
        rows = c.execute(
            f"SELECT * FROM merge_proposals WHERE {' AND '.join(where)} "
            "ORDER BY confidence DESC, created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def merge_proposal_get(proposal_uuid: str) -> dict | None:
    c = _conn()
    try:
        row = c.execute(
            "SELECT * FROM merge_proposals WHERE uuid = ?",
            (proposal_uuid,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def merge_proposal_update_status(proposal_uuid: str, status: str,
                                 reviewed_by: str | None = None,
                                 after_snapshot: dict | None = None):
    import json as _json
    c = _conn()
    try:
        c.execute(
            "UPDATE merge_proposals SET status = ?, reviewed_by = ?, reviewed_at = ?, "
            "after_snapshot = COALESCE(?, after_snapshot) WHERE uuid = ?",
            (status, reviewed_by, _now_iso(),
             _json.dumps(after_snapshot, ensure_ascii=False, default=str) if after_snapshot else None,
             proposal_uuid),
        )
        c.commit()
    finally:
        c.close()


def merge_blacklist_add(uuid_a: str, uuid_b: str, reason: str = "rejected"):
    a, b = sorted([uuid_a, uuid_b])
    c = _conn()
    try:
        c.execute(
            "INSERT OR IGNORE INTO merge_blacklist (uuid_a, uuid_b, reason, created_at) "
            "VALUES (?, ?, ?, ?)",
            (a, b, reason, _now_iso()),
        )
        c.commit()
    finally:
        c.close()


def merge_documents(keep_uuid: str, drop_uuid: str) -> dict:
    """Reassign products/contacts/document_tags/notes FK to keep_doc, delete drop_doc.

    Returns {moved_products, moved_contacts, moved_tags, moved_notes, dropped_id}.
    Atomic single-transaction.
    """
    c = _conn()
    try:
        keep_row = c.execute(
            "SELECT id FROM documents WHERE uuid = ?", (keep_uuid,)
        ).fetchone()
        drop_row = c.execute(
            "SELECT id FROM documents WHERE uuid = ?", (drop_uuid,)
        ).fetchone()
        if not keep_row or not drop_row:
            raise ValueError("keep or drop document not found")
        keep_id = keep_row["id"]
        drop_id = drop_row["id"]
        if keep_id == drop_id:
            raise ValueError("cannot merge document into itself")

        moved_p = c.execute(
            "UPDATE products SET document_uuid = ?, document_id = ? WHERE document_id = ?",
            (keep_uuid, keep_id, drop_id),
        ).rowcount
        moved_ct = c.execute(
            "UPDATE contacts SET document_uuid = ?, document_id = ? WHERE document_id = ?",
            (keep_uuid, keep_id, drop_id),
        ).rowcount
        moved_tags = 0
        moved_notes = 0
        try:
            moved_tags = c.execute(
                "UPDATE document_tags SET document_uuid = ? WHERE document_uuid = ?",
                (keep_uuid, drop_uuid),
            ).rowcount
        except Exception:
            pass
        try:
            moved_notes = c.execute(
                "UPDATE notes SET document_uuid = ? WHERE document_uuid = ?",
                (keep_uuid, drop_uuid),
            ).rowcount
        except Exception:
            pass

        c.execute("DELETE FROM documents WHERE id = ?", (drop_id,))
        c.commit()
        return {
            "moved_products": moved_p, "moved_contacts": moved_ct,
            "moved_tags": moved_tags, "moved_notes": moved_notes,
            "dropped_id": drop_id,
        }
    finally:
        c.close()


def _migrate_auth_tables(c):
    """Create users + login_attempts tables (idempotent)."""
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone_e164 TEXT UNIQUE,
            password_hash TEXT,
            pin_hash TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            created_by TEXT,
            last_login TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_e164);

        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT NOT NULL,
            ip TEXT,
            success INTEGER NOT NULL,
            at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_login_attempts_id_at ON login_attempts(identifier, at);
    """)
    c.commit()


# ─── Auth: users CRUD ────────────────────────────────────────────────
_USER_UPDATABLE = {"name", "email", "phone_e164", "password_hash", "pin_hash", "role", "is_active"}


def get_user_by_identifier(c, identifier_kind: str, value: str):
    if identifier_kind == "email":
        return c.execute("SELECT * FROM users WHERE email = ?", (value,)).fetchone()
    if identifier_kind == "phone":
        return c.execute("SELECT * FROM users WHERE phone_e164 = ?", (value,)).fetchone()
    return None


def get_user_by_uuid(c, user_uuid: str):
    return c.execute("SELECT * FROM users WHERE uuid = ?", (user_uuid,)).fetchone()


def create_user(c, name, email, phone_e164, password_hash, pin_hash, role, created_by):
    new_uuid = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT INTO users(uuid, name, email, phone_e164, password_hash, pin_hash, role, is_active, created_at, created_by) "
        "VALUES (?,?,?,?,?,?,?,1,?,?)",
        (new_uuid, name, email, phone_e164, password_hash, pin_hash, role, now, created_by),
    )
    c.commit()
    return new_uuid


def update_user(c, user_uuid: str, updates: dict) -> int:
    fields = {k: v for k, v in (updates or {}).items() if k in _USER_UPDATABLE}
    if not fields:
        return 0
    sets = ", ".join(f"{k} = ?" for k in fields.keys())
    params = list(fields.values()) + [user_uuid]
    cur = c.execute(f"UPDATE users SET {sets} WHERE uuid = ?", params)
    c.commit()
    return cur.rowcount


def list_users(c):
    return c.execute(
        "SELECT * FROM users ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, created_at"
    ).fetchall()


def delete_user(c, user_uuid: str) -> int:
    row = c.execute("SELECT role FROM users WHERE uuid = ?", (user_uuid,)).fetchone()
    if not row:
        return 0
    if row["role"] == "super_admin":
        raise ValueError("cannot delete super_admin")
    cur = c.execute("DELETE FROM users WHERE uuid = ?", (user_uuid,))
    c.commit()
    return cur.rowcount


def touch_login(c, user_uuid: str):
    now = datetime.now(timezone.utc).isoformat()
    c.execute("UPDATE users SET last_login = ? WHERE uuid = ?", (now, user_uuid))
    c.commit()


def insert_extraction(folder: str, record: dict, owner_uuid: str = None, is_shared: int = 0,
                      metadata_extra: dict = None):
    c = _conn()
    doc_uuid = str(uuid4())
    metadata_json = None
    if record.get("metadata"):
        metadata_json = json.dumps(record["metadata"], ensure_ascii=False)
    # Extract flat metadata fields
    meta = record.get("metadata", {}) or {}
    gps_lat = meta.get("gps_lat")
    gps_lng = meta.get("gps_lng")
    date_taken = meta.get("date_taken")
    camera_make = meta.get("camera_make")
    camera_model = meta.get("camera_model")
    img_width = meta.get("img_width") or meta.get("width")
    img_height = meta.get("img_height") or meta.get("height")
    file_size_kb = meta.get("file_size_kb")

    # Compute file_hash from source_path if it exists
    file_hash = None
    src_path = record.get("source_path", "") or ""
    if src_path and os.path.exists(src_path):
        try:
            file_hash = compute_file_hash(src_path)
        except Exception:
            file_hash = None

    # New optional doc columns
    qr_payloads = record.get("qr_payloads")
    if qr_payloads is not None and not isinstance(qr_payloads, str):
        qr_payloads = json.dumps(qr_payloads, ensure_ascii=False)
    catalog_url = record.get("catalog_url")
    source_channel = record.get("source_channel")
    source_sender = record.get("source_sender")

    # ── Expanded metadata (EXIF + geocode + quality + client) ──
    mx = metadata_extra or {}
    source_channel_val = mx.get("source_channel") or source_channel or "upload"
    _now = _now_iso()
    # Allow extra GPS/EXIF in metadata dict to override base meta if present
    gps_lat = mx.get("gps_lat", gps_lat)
    gps_lng = mx.get("gps_lng", gps_lng)
    gps_altitude = mx.get("gps_altitude") if mx.get("gps_altitude") is not None else meta.get("gps_altitude")
    gps_heading = mx.get("gps_heading") if mx.get("gps_heading") is not None else meta.get("gps_heading")
    gps_speed = mx.get("gps_speed") if mx.get("gps_speed") is not None else meta.get("gps_speed")
    gps_source = mx.get("gps_source")
    gps_accuracy = mx.get("gps_accuracy")
    country = mx.get("country")
    city = mx.get("city")
    address_full = mx.get("address_full")
    lens_model = mx.get("lens_model") if mx.get("lens_model") is not None else meta.get("lens_model")
    focal_length = mx.get("focal_length") if mx.get("focal_length") is not None else meta.get("focal_length")
    f_number = mx.get("f_number") if mx.get("f_number") is not None else meta.get("f_number")
    iso_v = mx.get("iso") if mx.get("iso") is not None else meta.get("iso")
    exposure_time = mx.get("exposure_time") if mx.get("exposure_time") is not None else meta.get("exposure_time")
    software = mx.get("software") if mx.get("software") is not None else meta.get("software")
    sub_sec_time = mx.get("sub_sec_time") if mx.get("sub_sec_time") is not None else meta.get("sub_sec_time")
    client_timezone = mx.get("client_timezone")
    client_user_agent = mx.get("client_user_agent")
    client_ip = mx.get("client_ip")
    client_timestamp = mx.get("client_timestamp")
    image_phash = mx.get("image_phash")
    blur_score = mx.get("blur_score")
    is_blurry_v = 1 if mx.get("is_blurry") else 0
    near_dup_of = mx.get("near_dup_of")
    device_signals = mx.get("device_signals")
    trade_show = mx.get("trade_show")

    c.execute("""
        INSERT OR REPLACE INTO documents
        (folder, source_file, source_path, image_type, company, title, products, contact, key_info, raw_text, full_json, uuid, metadata,
         gps_lat, gps_lng, date_taken, camera_make, camera_model, img_width, img_height, file_size_kb,
         catalog_url, qr_payloads, source_channel, source_sender, file_hash,
         owner_uuid, is_shared,
         gps_altitude, gps_heading, gps_speed, gps_source, gps_accuracy,
         country, city, address_full,
         lens_model, focal_length, f_number, iso, exposure_time, software, sub_sec_time,
         client_timezone, client_user_agent, client_ip, client_timestamp,
         image_phash, blur_score, is_blurry, near_dup_of, device_signals,
         updated_at, edit_count, trade_show,
         quality_score, needs_revision)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        folder,
        record.get("source_file", ""),
        record.get("source_path", ""),
        record.get("image_type", ""),
        record.get("company", ""),
        record.get("title", ""),
        json.dumps(record.get("products", []), ensure_ascii=False),
        json.dumps(record.get("contact", {}), ensure_ascii=False),
        json.dumps(record.get("key_info", []), ensure_ascii=False),
        record.get("raw_text", ""),
        json.dumps(record, ensure_ascii=False),
        doc_uuid,
        metadata_json,
        gps_lat, gps_lng, date_taken, camera_make, camera_model, img_width, img_height, file_size_kb,
        catalog_url, qr_payloads, source_channel_val, source_sender, file_hash,
        owner_uuid, int(bool(is_shared)),
        gps_altitude, gps_heading, gps_speed, gps_source, gps_accuracy,
        country, city, address_full,
        lens_model, focal_length, f_number, iso_v, exposure_time, software, sub_sec_time,
        client_timezone, client_user_agent, client_ip, client_timestamp,
        image_phash, blur_score, is_blurry_v, near_dup_of, device_signals,
        _now, 0, trade_show,
        record.get("quality_score"), int(bool(record.get("needs_revision"))),
    ))
    doc_id = c.execute("SELECT id FROM documents WHERE folder = ? AND source_file = ?",
                       (folder, record.get("source_file", ""))).fetchone()
    doc_id = doc_id[0] if doc_id else None
    source_file = record.get("source_file", "")
    company = record.get("company", "")

    # Insert products into normalized table
    products = record.get("products", [])
    if isinstance(products, str):
        try:
            products = json.loads(products)
        except Exception:
            products = []
    if isinstance(products, list):
        for p in products:
            if not isinstance(p, dict):
                continue
            p_name = p.get("product_name", "") or p.get("name", "")
            specs_val = p.get("specs", "")
            if not isinstance(specs_val, str):
                specs_val = json.dumps(specs_val, ensure_ascii=False)
            price_str = p.get("price", "")
            # Parse currency + numeric amount for filtering/aggregation
            try:
                from pipeline.pricing import parse_price as _parse_price
                ccy, amt = _parse_price(price_str)
            except Exception:
                ccy, amt = None, None
            try:
                c.execute("""
                    INSERT INTO products (uuid, document_uuid, document_id, folder, source_file, company, name, model, specs, category, price, image_desc, owner_uuid, is_shared,
                                          source_channel, updated_at, edit_count, currency, price_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid4()), doc_uuid, doc_id, folder, source_file,
                    p.get("company", "") or company,
                    p_name, p.get("model", ""), specs_val,
                    p.get("category", ""), price_str,
                    p.get("image_desc", "") or p.get("description", ""),
                    owner_uuid, int(bool(is_shared)),
                    source_channel_val, _now, 0,
                    ccy, amt,
                ))
            except Exception:
                pass  # Skip duplicates

    # Insert contact into normalized table
    contact = record.get("contact", {})
    if isinstance(contact, str):
        try:
            contact = json.loads(contact)
        except Exception:
            contact = {}
    if isinstance(contact, dict):
        # Cascade: contact.company → doc.company → first product.company →
        # website-domain → email-domain. Stops at first non-empty.
        try:
            from pipeline.company_resolver import resolve_company  # noqa: WPS433
            ct_company = resolve_company(
                contact=contact,
                doc_company=record.get("company") or "",
                products=products if isinstance(products, list) else [],
                website=(contact.get("website") or "").strip(),
                email=(contact.get("email") or "").strip(),
            )
        except Exception:
            ct_company = (contact.get("company") or record.get("company") or "").strip()
        if ct_company:
            contact["company"] = ct_company
        ct_person = contact.get("person", "") or ""
        ct_phone = contact.get("phone", "") or ""
        ct_email = contact.get("email", "") or ""
        ct_website = contact.get("website", "") or ""
        ct_address = contact.get("address", "") or ""
        if any([ct_company, ct_person, ct_phone, ct_email, ct_website, ct_address]) or any(
            contact.get(k) for k in ("wechat_id", "whatsapp", "telegram", "viber", "line_id",
                                      "signal_phone", "phone_e164", "messengers", "wechat_qr_url")
        ):
            # Commit pending doc insert first so upsert_contact's separate connection sees it
            c.commit()
            try:
                payload = dict(contact)
                payload["folder"] = folder
                payload["source_file"] = source_file
                upsert_contact(payload, document_uuid=doc_uuid, document_id=doc_id,
                               owner_uuid=owner_uuid, is_shared=int(bool(is_shared)),
                               source_channel=source_channel_val)
            except Exception:
                pass

    c.commit()
    c.close()


def load_all_extractions():
    """Load from JSON files into SQLite."""
    ext_dir = config.EXTRACTIONS_DIR
    count = 0
    for fname in os.listdir(ext_dir):
        if fname == "all_extractions.json" or not fname.endswith(".json"):
            continue
        folder = fname.replace(".json", "")
        with open(os.path.join(ext_dir, fname)) as f:
            records = json.load(f)
        for r in records:
            insert_extraction(folder, r)
            count += 1
    return count


def search(query: str, limit: int = 20) -> list:
    import re
    # Sanitize for FTS5: keep only alphanumeric and spaces, join words with OR
    words = re.findall(r'[a-zA-Z0-9]+', query)
    if not words:
        return []
    fts_query = " OR ".join(words)
    c = _conn()
    try:
        rows = c.execute("""
            SELECT d.* FROM documents_fts f
            JOIN documents d ON d.id = f.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank LIMIT ?
        """, (fts_query, limit)).fetchall()
    except Exception:
        rows = []
    c.close()
    return [dict(r) for r in rows]


def get_all(limit: int = 500) -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM documents ORDER BY folder, source_file LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_by_folder(folder: str) -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM documents WHERE folder = ? ORDER BY source_file", (folder,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    c = _conn()
    total = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    folders = c.execute("SELECT DISTINCT folder FROM documents").fetchall()
    companies = c.execute("SELECT DISTINCT company FROM documents WHERE company IS NOT NULL AND company != ''").fetchall()
    c.close()
    return {
        "total_documents": total,
        "folders": [r[0] for r in folders],
        "companies": [r[0] for r in companies],
    }


def save_chat(session_id: str, role: str, content: str, user_uuid: str = None):
    c = _conn()
    c.execute(
        "INSERT INTO chat_history (session_id, role, content, user_uuid) VALUES (?, ?, ?, ?)",
        (session_id, role, content, user_uuid),
    )
    c.commit()
    c.close()


def get_chat_history(session_id: str, limit: int = 50, user: dict = None) -> list:
    c = _conn()
    where = "session_id = ?"
    params = [session_id]
    if user and user.get("role") not in ("super_admin", "admin"):
        # Strict ownership — NULL rows are pre-backfill leftovers; treat as not-mine
        where += " AND user_uuid = ?"
        params.append(user["uuid"])
    rows = c.execute(
        f"SELECT role, content, created_at FROM chat_history WHERE {where} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in reversed(rows)]


def list_sessions(user: dict = None) -> list:
    c = _conn()
    where = ""
    params: list = []
    if user and user.get("role") not in ("super_admin", "admin"):
        where = "WHERE user_uuid = ?"
        params.append(user["uuid"])
    rows = c.execute(f"""
        SELECT session_id, MIN(created_at) as started, MAX(created_at) as last_msg,
               COUNT(*) as messages,
               (SELECT SUBSTR(content, 1, 50) FROM chat_history ch2
                WHERE ch2.session_id = chat_history.session_id AND ch2.role = 'user'
                ORDER BY ch2.id ASC LIMIT 1) as preview
        FROM chat_history {where} GROUP BY session_id ORDER BY last_msg DESC
    """, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def session_owner(session_id: str) -> str:
    """Return the user_uuid that owns a chat session (first non-null user_uuid)."""
    c = _conn()
    row = c.execute(
        "SELECT user_uuid FROM chat_history WHERE session_id = ? AND user_uuid IS NOT NULL LIMIT 1",
        (session_id,),
    ).fetchone()
    c.close()
    return row["user_uuid"] if row else None


def delete_session(session_id: str):
    c = _conn()
    c.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
    c.commit()
    c.close()


def queue_add(batch_id: str, file_name: str, file_path: str,
              source_channel: str = None, source_sender: str = None, file_hash: str = None,
              owner_uuid: str = None, trade_show: str = None):
    c = _conn()
    for col_def in ["source_channel TEXT", "source_sender TEXT", "file_hash TEXT",
                    "owner_uuid TEXT", "trade_show TEXT"]:
        try:
            c.execute(f"ALTER TABLE queue ADD COLUMN {col_def}")
            c.commit()
        except sqlite3.OperationalError:
            pass
    c.execute(
        "INSERT INTO queue (batch_id, file_name, file_path, source_channel, source_sender, "
        "file_hash, owner_uuid, trade_show) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (batch_id, file_name, file_path, source_channel, source_sender,
         file_hash, owner_uuid, trade_show),
    )
    c.commit()
    c.close()


def file_already_ingested(file_hash: str) -> bool:
    if not file_hash:
        return False
    c = _conn()
    try:
        row = c.execute("SELECT 1 FROM documents WHERE file_hash = ? LIMIT 1", (file_hash,)).fetchone()
        if row:
            c.close()
            return True
    except sqlite3.OperationalError:
        pass
    try:
        row = c.execute("SELECT 1 FROM queue WHERE file_hash = ? LIMIT 1", (file_hash,)).fetchone()
        c.close()
        return row is not None
    except sqlite3.OperationalError:
        c.close()
        return False


def wechat_map_get(chat_hash: str):
    c = _conn()
    row = c.execute("SELECT * FROM wechat_chat_map WHERE chat_hash = ?", (chat_hash,)).fetchone()
    c.close()
    return dict(row) if row else None


def wechat_map_upsert(chat_hash: str, vendor_company: str = None,
                     contact_uuid: str = None, notes: str = None) -> dict:
    c = _conn()
    existing = c.execute("SELECT * FROM wechat_chat_map WHERE chat_hash = ?", (chat_hash,)).fetchone()
    if existing:
        c.execute(
            "UPDATE wechat_chat_map SET vendor_company = COALESCE(?, vendor_company), "
            "contact_uuid = COALESCE(?, contact_uuid), notes = COALESCE(?, notes) "
            "WHERE chat_hash = ?",
            (vendor_company, contact_uuid, notes, chat_hash),
        )
    else:
        c.execute(
            "INSERT INTO wechat_chat_map (chat_hash, vendor_company, contact_uuid, notes) "
            "VALUES (?, ?, ?, ?)",
            (chat_hash, vendor_company, contact_uuid, notes),
        )
    c.commit()
    row = c.execute("SELECT * FROM wechat_chat_map WHERE chat_hash = ?", (chat_hash,)).fetchone()
    c.close()
    return dict(row) if row else {}


def wechat_map_delete(chat_hash: str) -> int:
    c = _conn()
    n = c.execute("DELETE FROM wechat_chat_map WHERE chat_hash = ?", (chat_hash,)).rowcount
    c.commit()
    c.close()
    return n


def wechat_map_list() -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM wechat_chat_map ORDER BY created_at DESC").fetchall()
    results = []
    for r in rows:
        d = dict(r)
        ch = d["chat_hash"]
        try:
            cnt = c.execute(
                "SELECT COUNT(*) FROM queue WHERE source_channel = 'wechat_desktop' "
                "AND (source_sender = ? OR source_sender = ?)",
                (ch, d.get("vendor_company") or ""),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            cnt = 0
        d["file_count"] = cnt
        results.append(d)
    c.close()
    return results


def update_contact(uuid: str, fields: dict) -> int:
    allowed = {"company", "person", "phone", "email", "website", "address",
               "wechat_id", "wechat_qr_url", "whatsapp", "viber", "telegram",
               "line_id", "signal_phone", "messengers", "phone_e164"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return 0
    c = _conn()
    cols = ", ".join(f"{k} = ?" for k in sets)
    vals = list(sets.values()) + [_now_iso(), uuid]
    n = c.execute(
        f"UPDATE contacts SET {cols}, updated_at = ?, "
        "edit_count = COALESCE(edit_count, 0) + 1 WHERE uuid = ?",
        vals,
    ).rowcount
    c.commit()
    c.close()
    return n


def update_product(uuid: str, fields: dict) -> int:
    allowed = {"company", "name", "model", "specs", "category", "price", "image_desc"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return 0
    c = _conn()
    cols = ", ".join(f"{k} = ?" for k in sets)
    vals = list(sets.values()) + [_now_iso(), uuid]
    n = c.execute(
        f"UPDATE products SET {cols}, updated_at = ?, "
        "edit_count = COALESCE(edit_count, 0) + 1 WHERE uuid = ?",
        vals,
    ).rowcount
    c.commit()
    c.close()
    return n


def get_contact_by_uuid(uuid: str):
    c = _conn()
    row = c.execute("SELECT * FROM contacts WHERE uuid = ?", (uuid,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_all_contact_records() -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM contacts").fetchall()
    c.close()
    return [dict(r) for r in rows]


def merge_contacts(keep_uuid: str, merge_uuid: str) -> dict:
    c = _conn()
    keep = c.execute("SELECT * FROM contacts WHERE uuid = ?", (keep_uuid,)).fetchone()
    drop = c.execute("SELECT * FROM contacts WHERE uuid = ?", (merge_uuid,)).fetchone()
    if not keep or not drop:
        c.close()
        return {"merged": False, "reason": "uuid not found"}
    keep_d = dict(keep)
    drop_d = dict(drop)
    fillable = ["company", "person", "phone", "email", "website", "address",
                "wechat_id", "wechat_qr_url", "whatsapp", "viber", "telegram",
                "line_id", "signal_phone", "messengers", "phone_e164"]
    updates = {}
    for f in fillable:
        if not keep_d.get(f) and drop_d.get(f):
            updates[f] = drop_d[f]
    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [keep_uuid]
        c.execute(f"UPDATE contacts SET {cols} WHERE uuid = ?", vals)
    c.execute("DELETE FROM contacts WHERE uuid = ?", (merge_uuid,))
    c.commit()
    c.close()
    return {"merged": True, "filled": list(updates.keys())}


def get_document(doc_id: int):
    c = _conn()
    row = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def update_document_qr(doc_id: int, qr_payloads: list) -> int:
    c = _conn()
    n = c.execute(
        "UPDATE documents SET qr_payloads = ? WHERE id = ?",
        (json.dumps(qr_payloads, ensure_ascii=False), doc_id),
    ).rowcount
    c.commit()
    c.close()
    return n


def queue_pending(batch_id: str = None) -> list:
    c = _conn()
    if batch_id:
        rows = c.execute("SELECT * FROM queue WHERE batch_id = ? AND status = 'pending' ORDER BY id", (batch_id,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM queue WHERE status = 'pending' ORDER BY id").fetchall()
    c.close()
    return [dict(r) for r in rows]


def queue_delete_by_id(queue_id: int) -> int:
    c = _conn()
    try:
        n = c.execute("DELETE FROM queue WHERE id = ?", (queue_id,)).rowcount
        c.commit()
    finally:
        c.close()
    return n


def queue_update(queue_id: int, status: str, image_type: str = None, error: str = None):
    c = _conn()
    c.execute("UPDATE queue SET status = ?, image_type = ?, error = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
              (status, image_type, error, queue_id))
    c.commit()
    c.close()


def queue_errors(batch_id: str = None) -> list:
    c = _conn()
    if batch_id:
        rows = c.execute("SELECT * FROM queue WHERE batch_id = ? AND status = 'error' ORDER BY id", (batch_id,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM queue WHERE status = 'error' ORDER BY id").fetchall()
    c.close()
    return [dict(r) for r in rows]


def queue_retry(queue_id: int):
    c = _conn()
    c.execute("UPDATE queue SET status = 'pending', error = NULL, processed_at = NULL WHERE id = ? AND status = 'error'",
              (queue_id,))
    c.commit()
    changed = c.total_changes
    c.close()
    return changed > 0


def queue_status(batch_id: str = None) -> dict:
    c = _conn()
    if batch_id:
        rows = c.execute("SELECT status, COUNT(*) as cnt FROM queue WHERE batch_id = ? GROUP BY status", (batch_id,)).fetchall()
        total = c.execute("SELECT COUNT(*) FROM queue WHERE batch_id = ?", (batch_id,)).fetchone()[0]
    else:
        rows = c.execute("SELECT status, COUNT(*) as cnt FROM queue GROUP BY status").fetchall()
        total = c.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    c.close()
    breakdown = {r["status"]: r["cnt"] for r in rows}
    return {"total": total, **breakdown}


def delete_batch(batch_id: str) -> int:
    c = _conn()
    queue_deleted = c.execute("DELETE FROM queue WHERE batch_id = ?", (batch_id,)).rowcount
    doc_deleted = c.execute("DELETE FROM documents WHERE folder = ?", (batch_id,)).rowcount
    c.commit()
    c.close()
    return queue_deleted + doc_deleted


def get_document(doc_uuid: str) -> dict | None:
    c = _conn()
    try:
        row = c.execute("SELECT * FROM documents WHERE uuid = ?", (doc_uuid,)).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def delete_document(doc_uuid: str) -> dict:
    """Delete one document + its products/contacts/tags. Returns {folder, source_file, deleted}."""
    c = _conn()
    try:
        row = c.execute(
            "SELECT id, folder, source_file FROM documents WHERE uuid = ?", (doc_uuid,)
        ).fetchone()
        if not row:
            return {"deleted": 0}
        doc_id, folder, source_file = row["id"], row["folder"], row["source_file"]
        c.execute("DELETE FROM products WHERE document_uuid = ?", (doc_uuid,))
        c.execute("DELETE FROM contacts WHERE document_uuid = ?", (doc_uuid,))
        try:
            c.execute("DELETE FROM document_tags WHERE document_uuid = ?", (doc_uuid,))
        except Exception:
            pass
        n = c.execute("DELETE FROM documents WHERE uuid = ?", (doc_uuid,)).rowcount
        c.commit()
        return {"deleted": n, "folder": folder, "source_file": source_file}
    finally:
        c.close()


def queue_batches(user: dict = None) -> list:
    c = _conn()
    where = ""
    params: tuple = ()
    if user and user.get("role") not in ("super_admin", "admin"):
        where = "WHERE q.owner_uuid = ?"
        params = (user["uuid"],)
    rows = c.execute(f"""
        SELECT q.batch_id, COUNT(*) as total,
               SUM(CASE WHEN q.status='pending' THEN 1 ELSE 0 END) as pending,
               SUM(CASE WHEN q.status='done' THEN 1 ELSE 0 END) as done,
               SUM(CASE WHEN q.status='error' THEN 1 ELSE 0 END) as errors,
               MIN(q.created_at) as created, MAX(q.processed_at) as last_processed,
               MAX(q.owner_uuid) as owner_uuid,
               MAX(u.name) as owner_name,
               MAX(q.trade_show) as trade_show
        FROM queue q
        LEFT JOIN users u ON u.uuid = q.owner_uuid
        {where} GROUP BY q.batch_id ORDER BY created DESC
    """, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_all_contacts() -> list:
    """Parse contact JSON from all documents and return a flat list of contacts."""
    c = _conn()
    rows = c.execute("SELECT folder, source_file, contact FROM documents ORDER BY folder, source_file").fetchall()
    c.close()
    contacts = []
    for r in rows:
        raw = r["contact"]
        if not raw:
            continue
        try:
            ct = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if not isinstance(ct, dict):
            continue
        company = ct.get("company", "") or ""
        person = ct.get("person", "") or ""
        phone = ct.get("phone", "") or ""
        email = ct.get("email", "") or ""
        website = ct.get("website", "") or ""
        address = ct.get("address", "") or ""
        # Skip if all contact fields are empty
        if not any([company, person, phone, email, website, address]):
            continue
        contacts.append({
            "company": company,
            "person": person,
            "phone": phone,
            "email": email,
            "website": website,
            "address": address,
            "folder": r["folder"],
            "source_file": r["source_file"],
        })
    return contacts


def get_dashboard_stats() -> dict:
    """Return rich dashboard statistics."""
    c = _conn()
    total_documents = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    # Count products by parsing JSON
    rows = c.execute("SELECT folder, company, products FROM documents ORDER BY folder, company").fetchall()
    total_products = 0
    company_map = {}  # company -> {doc_count, product_count}
    for r in rows:
        company = r["company"] or "Unknown"
        if company not in company_map:
            company_map[company] = {"doc_count": 0, "product_count": 0}
        company_map[company]["doc_count"] += 1
        prods = r["products"]
        if prods:
            try:
                p = json.loads(prods) if isinstance(prods, str) else prods
                if isinstance(p, list):
                    total_products += len(p)
                    company_map[company]["product_count"] += len(p)
            except Exception:
                pass

    companies_with_counts = [
        {"company": k, "doc_count": v["doc_count"], "product_count": v["product_count"]}
        for k, v in sorted(company_map.items())
    ]

    # Type breakdown
    type_rows = c.execute(
        "SELECT image_type, COUNT(*) as cnt FROM documents GROUP BY image_type ORDER BY cnt DESC"
    ).fetchall()
    type_breakdown = [{"image_type": r["image_type"] or "unknown", "count": r["cnt"]} for r in type_rows]

    # Folder breakdown
    folder_rows = c.execute(
        "SELECT folder, COUNT(*) as cnt FROM documents GROUP BY folder ORDER BY cnt DESC"
    ).fetchall()
    folder_breakdown = [{"folder": r["folder"], "count": r["cnt"]} for r in folder_rows]

    # Recent uploads (last 5 queue items)
    recent_rows = c.execute(
        "SELECT id, batch_id, file_name, status, image_type, created_at, processed_at "
        "FROM queue ORDER BY id DESC LIMIT 5"
    ).fetchall()
    recent_uploads = [dict(r) for r in recent_rows]

    c.close()
    return {
        "total_documents": total_documents,
        "total_products": total_products,
        "companies_with_counts": companies_with_counts,
        "type_breakdown": type_breakdown,
        "folder_breakdown": folder_breakdown,
        "recent_uploads": recent_uploads,
    }


def export_all() -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM documents ORDER BY folder, source_file").fetchall()
    c.close()
    results = []
    for r in rows:
        d = dict(r)
        for field in ("products", "contact", "key_info"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        results.append(d)
    return results


def populate_normalized_tables() -> dict:
    """Migrate existing documents into the normalized products and contacts tables."""
    c = _conn()
    # Only process documents that don't yet have a uuid (i.e., not yet migrated)
    rows = c.execute("SELECT * FROM documents WHERE uuid IS NULL").fetchall()
    products_added = 0
    contacts_added = 0

    for row in rows:
        doc_id = row["id"]
        folder = row["folder"]
        source_file = row["source_file"]
        company = row["company"] or ""

        # Assign uuid to document
        doc_uuid = None
        if not doc_uuid:
            doc_uuid = str(uuid4())
            c.execute("UPDATE documents SET uuid = ? WHERE id = ?", (doc_uuid, doc_id))

        # Parse and insert products
        raw_products = row["products"]
        if raw_products:
            try:
                products = json.loads(raw_products) if isinstance(raw_products, str) else raw_products
            except Exception:
                products = []
            if isinstance(products, list):
                for p in products:
                    if not isinstance(p, dict):
                        continue
                    p_name = p.get("product_name", "") or p.get("name", "")
                    specs_val = p.get("specs", "")
                    if not isinstance(specs_val, str):
                        specs_val = json.dumps(specs_val, ensure_ascii=False)
                    try:
                        c.execute("""
                            INSERT INTO products (uuid, document_uuid, document_id, folder, source_file, company, name, model, specs, category, price, image_desc)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(uuid4()), doc_uuid, doc_id, folder, source_file,
                            p.get("company", "") or company,
                            p_name, p.get("model", ""), specs_val,
                            p.get("category", ""), p.get("price", ""),
                            p.get("image_desc", "") or p.get("description", ""),
                        ))
                        products_added += 1
                    except Exception:
                        pass  # duplicate or other error

        # Parse and insert contacts
        raw_contact = row["contact"]
        if raw_contact:
            try:
                ct = json.loads(raw_contact) if isinstance(raw_contact, str) else raw_contact
            except Exception:
                ct = {}
            if isinstance(ct, dict):
                ct_company = ct.get("company", "") or ""
                ct_person = ct.get("person", "") or ""
                ct_phone = ct.get("phone", "") or ""
                ct_email = ct.get("email", "") or ""
                ct_website = ct.get("website", "") or ""
                ct_address = ct.get("address", "") or ""
                if any([ct_company, ct_person, ct_phone, ct_email, ct_website, ct_address]):
                    try:
                        c.execute("""
                            INSERT INTO contacts (uuid, document_uuid, document_id, folder, source_file, company, person, phone, email, website, address)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(uuid4()), doc_uuid, doc_id, folder, source_file,
                            ct_company, ct_person, ct_phone, ct_email, ct_website, ct_address,
                        ))
                        contacts_added += 1
                    except Exception:
                        pass

    c.commit()
    c.close()
    return {"products_added": products_added, "contacts_added": contacts_added}


def get_products_table(limit: int = 500) -> list:
    """SELECT from the normalized products table."""
    c = _conn()
    rows = c.execute("SELECT * FROM products ORDER BY company, name LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_contacts_table(limit: int = 500) -> list:
    """SELECT from the normalized contacts table."""
    c = _conn()
    rows = c.execute("SELECT * FROM contacts ORDER BY company, person LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_documents_with_metadata(limit: int = 500) -> list:
    """Return documents with parsed metadata."""
    c = _conn()
    rows = c.execute(
        "SELECT id, uuid, folder, source_file, image_type, company, metadata, created_at FROM documents ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    c.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                d["metadata"] = {}
        else:
            d["metadata"] = {}
        results.append(d)
    return results


def backfill_metadata_columns():
    """Read the metadata JSON column for all documents and populate the flat metadata columns."""
    c = _conn()
    rows = c.execute(
        "SELECT id, metadata FROM documents WHERE metadata IS NOT NULL AND gps_lat IS NULL AND camera_make IS NULL AND date_taken IS NULL"
    ).fetchall()
    for row in rows:
        try:
            meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        c.execute("""
            UPDATE documents SET
                gps_lat = ?, gps_lng = ?, date_taken = ?, camera_make = ?,
                camera_model = ?, img_width = ?, img_height = ?, file_size_kb = ?
            WHERE id = ?
        """, (
            meta.get("gps_lat"), meta.get("gps_lng"), meta.get("date_taken"),
            meta.get("camera_make"), meta.get("camera_model"),
            meta.get("img_width"), meta.get("img_height"), meta.get("file_size_kb"),
            row["id"],
        ))
    c.commit()
    c.close()


# ---------------------------------------------------------------------------
# File hash / dedup helpers
# ---------------------------------------------------------------------------
def compute_file_hash(path: str) -> str:
    """SHA256 of a file, streamed in 64KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def file_already_ingested(file_hash: str) -> bool:
    if not file_hash:
        return False
    c = _conn()
    row = c.execute("SELECT 1 FROM documents WHERE file_hash = ? LIMIT 1", (file_hash,)).fetchone()
    c.close()
    return row is not None


# ---------------------------------------------------------------------------
# Contact dedup / upsert
# ---------------------------------------------------------------------------
_CONTACT_MUTABLE_FIELDS = (
    "company", "person", "phone", "email", "website", "address",
    "wechat_id", "wechat_qr_url", "whatsapp", "viber", "telegram",
    "line_id", "signal_phone", "phone_e164",
)


def _merge_messengers(existing_json: str, new_list) -> str:
    """Merge messenger entries deduped by (platform, handle)."""
    try:
        existing = json.loads(existing_json) if existing_json else []
    except Exception:
        existing = []
    if not isinstance(existing, list):
        existing = []
    if not isinstance(new_list, list):
        new_list = []
    seen = set()
    merged = []
    for entry in list(existing) + list(new_list):
        if not isinstance(entry, dict):
            continue
        key = (entry.get("platform", ""), entry.get("handle", ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return json.dumps(merged, ensure_ascii=False)


def upsert_contact(c_data: dict, document_uuid: str = None, document_id: int = None,
                   owner_uuid: str = None, is_shared: int = 0,
                   source_channel: str = "upload") -> str:
    """Dedup contact insert. Returns contact uuid.

    Match order:
      1. phone_e164
      2. email
      3. (company AND person) fuzzy (lower+strip)
    On match: only fill NULL/empty existing fields with new non-null values;
    append messengers JSON (dedup by platform+handle).
    """
    if not isinstance(c_data, dict):
        c_data = {}

    conn = _conn()
    existing = None

    phone_e164 = (c_data.get("phone_e164") or "").strip()
    email = (c_data.get("email") or "").strip()
    company = (c_data.get("company") or "").strip()
    person = (c_data.get("person") or "").strip()

    if phone_e164:
        existing = conn.execute(
            "SELECT * FROM contacts WHERE phone_e164 = ? LIMIT 1", (phone_e164,)
        ).fetchone()
    if not existing and email:
        existing = conn.execute(
            "SELECT * FROM contacts WHERE LOWER(TRIM(email)) = LOWER(TRIM(?)) LIMIT 1", (email,)
        ).fetchone()
    if not existing and company and person:
        existing = conn.execute(
            "SELECT * FROM contacts WHERE LOWER(TRIM(company)) = LOWER(TRIM(?)) "
            "AND LOWER(TRIM(person)) = LOWER(TRIM(?)) LIMIT 1",
            (company, person),
        ).fetchone()

    if existing:
        contact_uuid = existing["uuid"]
        existing_d = dict(existing)
        updates = {}
        for field in _CONTACT_MUTABLE_FIELDS:
            new_val = c_data.get(field)
            if new_val is None or (isinstance(new_val, str) and not new_val.strip()):
                continue
            cur_val = existing_d.get(field)
            if cur_val is None or (isinstance(cur_val, str) and not cur_val.strip()):
                updates[field] = new_val

        new_messengers = c_data.get("messengers")
        if new_messengers is not None:
            merged_json = _merge_messengers(existing_d.get("messengers") or "[]", new_messengers)
            updates["messengers"] = merged_json

        if updates:
            # Audit: bump edit_count, set updated_at
            sets = ", ".join(f"{k} = ?" for k in updates)
            params = list(updates.values()) + [_now_iso(), contact_uuid]
            conn.execute(
                f"UPDATE contacts SET {sets}, updated_at = ?, "
                "edit_count = COALESCE(edit_count, 0) + 1 WHERE uuid = ?",
                params,
            )
            conn.commit()
        conn.close()
        return contact_uuid

    # No match - insert new
    new_uuid = str(uuid4())
    messengers_val = c_data.get("messengers")
    if messengers_val is not None and not isinstance(messengers_val, str):
        messengers_val = json.dumps(messengers_val, ensure_ascii=False)

    # Look up owner name for cached column
    owner_name = None
    if owner_uuid:
        try:
            u = conn.execute("SELECT name FROM users WHERE uuid = ?", (owner_uuid,)).fetchone()
            if u:
                owner_name = u["name"]
        except Exception:
            owner_name = None

    _ins_now = _now_iso()
    conn.execute(
        """
        INSERT INTO contacts (
            uuid, document_uuid, document_id, folder, source_file,
            company, person, phone, email, website, address,
            wechat_id, wechat_qr_url, whatsapp, viber, telegram,
            line_id, signal_phone, messengers, phone_e164,
            owner_uuid, is_shared,
            source_channel, updated_at, edit_count, owner_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_uuid, document_uuid, document_id,
            c_data.get("folder", ""), c_data.get("source_file", ""),
            company, person,
            c_data.get("phone", "") or "",
            email,
            c_data.get("website", "") or "",
            c_data.get("address", "") or "",
            c_data.get("wechat_id"), c_data.get("wechat_qr_url"),
            c_data.get("whatsapp"), c_data.get("viber"), c_data.get("telegram"),
            c_data.get("line_id"), c_data.get("signal_phone"),
            messengers_val, phone_e164 or None,
            owner_uuid, int(bool(is_shared)),
            source_channel or "upload", _ins_now, 0, owner_name,
        ),
    )
    conn.commit()
    conn.close()
    return new_uuid


# ---------------------------------------------------------------------------
# WeChat chat map helpers
# ---------------------------------------------------------------------------
def wechat_map_get(chat_hash: str):
    c = _conn()
    row = c.execute("SELECT * FROM wechat_chat_map WHERE chat_hash = ?", (chat_hash,)).fetchone()
    c.close()
    return dict(row) if row else None


def wechat_map_set(chat_hash: str, vendor_company: str, contact_uuid: str = None, notes: str = None):
    c = _conn()
    c.execute(
        """
        INSERT INTO wechat_chat_map (chat_hash, vendor_company, contact_uuid, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_hash) DO UPDATE SET
            vendor_company = excluded.vendor_company,
            contact_uuid = excluded.contact_uuid,
            notes = excluded.notes
        """,
        (chat_hash, vendor_company, contact_uuid, notes),
    )
    c.commit()
    c.close()


def wechat_map_list() -> list:
    c = _conn()
    rows = c.execute("SELECT * FROM wechat_chat_map ORDER BY created_at DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]


def wechat_map_delete(chat_hash: str):
    c = _conn()
    c.execute("DELETE FROM wechat_chat_map WHERE chat_hash = ?", (chat_hash,))
    c.commit()
    c.close()


# ---------------------------------------------------------------------------
# Phone normalization migration
# ---------------------------------------------------------------------------
def migrate_phone_e164(default_region: str = "CN") -> dict:
    """Iterate existing contacts and populate phone_e164 from `phone` via phonenumbers."""
    try:
        import phonenumbers
    except ImportError:
        return {"updated": 0, "error": "phonenumbers not installed"}

    c = _conn()
    rows = c.execute(
        "SELECT id, phone FROM contacts WHERE (phone_e164 IS NULL OR phone_e164 = '') AND phone IS NOT NULL AND phone != ''"
    ).fetchall()
    updated = 0
    for r in rows:
        raw = r["phone"]
        if not raw:
            continue
        try:
            num = phonenumbers.parse(raw, default_region)
            if not phonenumbers.is_valid_number(num):
                continue
            e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
            c.execute("UPDATE contacts SET phone_e164 = ? WHERE id = ?", (e164, r["id"]))
            updated += 1
        except Exception:
            continue
    c.commit()
    c.close()
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Time-zone helper
# ---------------------------------------------------------------------------
def get_docs_by_local_date(date_str: str, tz: str = "Asia/Shanghai") -> list:
    """Return documents whose `date_taken` falls on `date_str` (YYYY-MM-DD) in the given tz.

    `date_taken` is stored as EXIF format e.g. '2026:04:22 14:33:01' (assumed UTC-naive).
    We convert the local day window to UTC and compare.
    """
    # Tz offset (fallback to fixed Asia/Shanghai +08:00 if zoneinfo absent)
    try:
        from zoneinfo import ZoneInfo
        tzinfo = ZoneInfo(tz)
    except Exception:
        tzinfo = timezone(timedelta(hours=8))

    try:
        local_day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tzinfo)
    except ValueError:
        return []
    local_next = local_day + timedelta(days=1)
    utc_start = local_day.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
    utc_end = local_next.astimezone(timezone.utc).strftime("%Y:%m:%d %H:%M:%S")

    c = _conn()
    rows = c.execute(
        "SELECT * FROM documents WHERE date_taken IS NOT NULL AND date_taken >= ? AND date_taken < ? ORDER BY date_taken",
        (utc_start, utc_end),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tenancy-aware query helpers (used by main.py endpoints)
# ---------------------------------------------------------------------------

def get_documents_visible(user: dict, folder: str = None, limit: int = 500) -> list:
    c = _conn()
    where_parts = []
    params = []
    if folder:
        where_parts.append("d.folder = ?")
        params.append(folder)
    vc, vp = visibility_clause("d", user)
    if vc:
        where_parts.append(vc)
        params.extend(vp)
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = c.execute(
        f"SELECT d.*, u.name AS owner_name FROM documents d "
        f"LEFT JOIN users u ON u.uuid = d.owner_uuid "
        f"{where_sql} ORDER BY d.folder, d.source_file LIMIT ?",
        (*params, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_document_visible(doc_id: int, user: dict):
    c = _conn()
    vc, vp = visibility_clause("", user)
    if vc:
        row = c.execute(f"SELECT * FROM documents WHERE id = ? AND {vc}", (doc_id, *vp)).fetchone()
    else:
        row = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_contact_visible(uuid: str, user: dict):
    c = _conn()
    vc, vp = visibility_clause("", user)
    if vc:
        row = c.execute(f"SELECT * FROM contacts WHERE uuid = ? AND {vc}", (uuid, *vp)).fetchone()
    else:
        row = c.execute("SELECT * FROM contacts WHERE uuid = ?", (uuid,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_product_visible(uuid: str, user: dict):
    c = _conn()
    vc, vp = visibility_clause("", user)
    if vc:
        row = c.execute(f"SELECT * FROM products WHERE uuid = ? AND {vc}", (uuid, *vp)).fetchone()
    else:
        row = c.execute("SELECT * FROM products WHERE uuid = ?", (uuid,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_product_by_uuid(uuid: str):
    c = _conn()
    row = c.execute("SELECT * FROM products WHERE uuid = ?", (uuid,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_contacts_table_visible(user: dict, limit: int = 500) -> list:
    c = _conn()
    vc, vp = visibility_clause("ct", user)
    where_sql = f"WHERE {vc}" if vc else ""
    rows = c.execute(
        f"SELECT ct.*, COALESCE(ct.owner_name, u.name) AS owner_name "
        f"FROM contacts ct LEFT JOIN users u ON u.uuid = ct.owner_uuid "
        f"{where_sql} ORDER BY ct.company, ct.person LIMIT ?",
        (*vp, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_products_table_visible(user: dict, limit: int = 500) -> list:
    c = _conn()
    vc, vp = visibility_clause("p", user)
    where_sql = f"WHERE {vc}" if vc else ""
    rows = c.execute(
        f"SELECT p.*, u.name AS owner_name FROM products p "
        f"LEFT JOIN users u ON u.uuid = p.owner_uuid "
        f"{where_sql} ORDER BY p.company, p.name LIMIT ?",
        (*vp, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_queue_visible(user: dict, batch_id: str = None) -> list:
    c = _conn()
    parts = []
    params = []
    if batch_id:
        parts.append("batch_id = ?")
        params.append(batch_id)
    if user and user.get("role") not in ("super_admin", "admin"):
        parts.append("owner_uuid = ?")
        params.append(user["uuid"])
    where_sql = ("WHERE " + " AND ".join(parts)) if parts else ""
    rows = c.execute(f"SELECT * FROM queue {where_sql} ORDER BY id DESC", params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_stats_visible(user: dict) -> dict:
    c = _conn()
    vc, vp = visibility_clause("", user)
    where_sql = f"WHERE {vc}" if vc else ""
    total = c.execute(f"SELECT COUNT(*) FROM documents {where_sql}", vp).fetchone()[0]
    folders = c.execute(
        f"SELECT DISTINCT folder FROM documents {where_sql}", vp
    ).fetchall()
    if vc:
        comp_sql = f"SELECT DISTINCT company FROM documents WHERE {vc} AND company IS NOT NULL AND company != ''"
    else:
        comp_sql = "SELECT DISTINCT company FROM documents WHERE company IS NOT NULL AND company != ''"
    companies = c.execute(comp_sql, vp).fetchall()
    c.close()
    return {
        "total_documents": total,
        "folders": [r[0] for r in folders],
        "companies": [r[0] for r in companies],
    }


def export_all_visible(user: dict) -> list:
    c = _conn()
    vc, vp = visibility_clause("", user)
    where_sql = f"WHERE {vc}" if vc else ""
    rows = c.execute(
        f"SELECT * FROM documents {where_sql} ORDER BY folder, source_file", vp
    ).fetchall()
    c.close()
    results = []
    for r in rows:
        d = dict(r)
        for field in ("products", "contact", "key_info"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        results.append(d)
    return results


def get_all_contact_records_visible(user: dict) -> list:
    c = _conn()
    vc, vp = visibility_clause("", user)
    where_sql = f"WHERE {vc}" if vc else ""
    rows = c.execute(f"SELECT * FROM contacts {where_sql}", vp).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Share toggle helpers ────────────────────────────────────────

def set_document_shared(doc_id: int, is_shared: bool) -> int:
    c = _conn()
    n = c.execute("UPDATE documents SET is_shared = ? WHERE id = ?",
                  (1 if is_shared else 0, doc_id)).rowcount
    c.commit()
    c.close()
    return n


def set_contact_shared(uuid: str, is_shared: bool) -> int:
    c = _conn()
    n = c.execute("UPDATE contacts SET is_shared = ? WHERE uuid = ?",
                  (1 if is_shared else 0, uuid)).rowcount
    c.commit()
    c.close()
    return n


def set_product_shared(uuid: str, is_shared: bool) -> int:
    c = _conn()
    n = c.execute("UPDATE products SET is_shared = ? WHERE uuid = ?",
                  (1 if is_shared else 0, uuid)).rowcount
    c.commit()
    c.close()
    return n


def delete_contact(uuid: str) -> int:
    c = _conn()
    n = c.execute("DELETE FROM contacts WHERE uuid = ?", (uuid,)).rowcount
    c.commit()
    c.close()
    return n


def delete_product(uuid: str) -> int:
    c = _conn()
    n = c.execute("DELETE FROM products WHERE uuid = ?", (uuid,)).rowcount
    c.commit()
    c.close()
    return n


init_db()
backfill_metadata_columns()
populate_normalized_tables()
