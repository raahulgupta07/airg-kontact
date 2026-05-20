"""
SQL tool system for KONTACT — gives the chat agent structured access
to the catalog database via read-only SQL, schema introspection, and
a pre-built summary.
"""

import sqlite3
import json
import os
import re
import httpx
import config

DB_PATH = os.path.join(config.DATA_DIR, "kontact.db")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def _rows_to_markdown(rows: list, columns: list[str]) -> str:
    """Convert a list of sqlite3.Row objects into a markdown table string."""
    if not rows:
        return "_No results._"

    # Header
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]

    for row in rows:
        cells = []
        for col in columns:
            val = row[col]
            if val is None:
                cells.append("")
            else:
                # Truncate long values so the table stays readable
                s = str(val)
                if len(s) > 120:
                    s = s[:117] + "..."
                # Escape pipes inside cell values
                s = s.replace("|", "\\|").replace("\n", " ")
                cells.append(s)
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 1 — query_catalog_db
# ---------------------------------------------------------------------------

_BLOCKED_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
                     "REPLACE", "ATTACH", "DETACH", "VACUUM", "REINDEX",
                     "PRAGMA"}

# Strict UUID v4 pattern: 8-4-4-4-12 hex with version/variant nibble checks loosened
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

_TENANCY_TABLES = ("documents", "contacts", "products")


def query_catalog_db(sql: str, user: dict = None) -> str:
    """
    Execute a read-only SQL query against kontact.db and return the results
    as a markdown table.  Max 50 rows.  Only SELECT / WITH statements are
    permitted.

    Tenancy: non-admin users get bare references to documents/contacts/products
    rewritten to user-scoped TEMP VIEWs that strictly pre-filter by owner_uuid.
    """
    sql = sql.strip().rstrip(";")

    # Basic write-protection
    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        return "Error: Only SELECT / WITH queries are allowed."

    upper_sql = sql.upper()
    for kw in _BLOCKED_KEYWORDS:
        if f" {kw} " in f" {upper_sql} " or upper_sql.startswith(kw):
            return f"Error: `{kw}` statements are not allowed (read-only mode)."

    # Enforce row limit
    if "LIMIT" not in upper_sql:
        sql += " LIMIT 50"

    conn = _conn()
    try:
        # Tenancy view rewrite for non-admin
        if user and user.get("role") not in ("super_admin", "admin"):
            uid = (user.get("uuid") or "").lower()
            # Defence in depth: regex + strict parse via uuid.UUID
            if not UUID_RE.match(uid):
                return "Error: invalid session"
            try:
                import uuid as _uuid
                _uuid.UUID(uid)
            except Exception:
                return "Error: invalid session"
            for t in _TENANCY_TABLES:
                try:
                    conn.execute(f"DROP VIEW IF EXISTS user_{t}")
                    # uid is now a validated UUID — no injection vector
                    conn.execute(
                        f"CREATE TEMP VIEW user_{t} AS "
                        f"SELECT * FROM {t} WHERE owner_uuid = '{uid}'"
                    )
                except Exception:
                    pass
            # rewrite bare table names → view names (word-boundary, case-insensitive)
            for t in _TENANCY_TABLES:
                sql = re.sub(rf'\b{t}\b', f'user_{t}', sql, flags=re.IGNORECASE)

        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            return "_Query returned no rows._"
        columns = [desc[0] for desc in cursor.description]
        return _rows_to_markdown(rows, columns)
    except Exception as e:
        return f"SQL error: {e}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool 2 — introspect_schema
# ---------------------------------------------------------------------------

def introspect_schema(table_name: str = None) -> str:
    """
    If table_name is None, list every table in the database.
    If table_name is given, show columns with types, the row count,
    and 3 sample rows.
    """
    conn = _conn()
    try:
        if table_name is None:
            rows = conn.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') ORDER BY name"
            ).fetchall()
            if not rows:
                return "_No tables found._"
            lines = ["| Table | Type |", "| --- | --- |"]
            for r in rows:
                lines.append(f"| {r['name']} | {r['type']} |")
            return "\n".join(lines)

        # --- specific table ---
        cols = conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
        if not cols:
            return f"Error: Table `{table_name}` not found."

        lines = [f"### Table: `{table_name}`\n"]
        lines.append("| # | Column | Type | Nullable | Default | PK |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for c in cols:
            nullable = "YES" if c["notnull"] == 0 else "NO"
            default = c["dflt_value"] if c["dflt_value"] is not None else ""
            pk = "YES" if c["pk"] else ""
            lines.append(
                f"| {c['cid']} | {c['name']} | {c['type']} "
                f"| {nullable} | {default} | {pk} |"
            )

        # Row count
        try:
            count = conn.execute(
                f"SELECT COUNT(*) as cnt FROM [{table_name}]"
            ).fetchone()["cnt"]
            lines.append(f"\n**Row count:** {count:,}")
        except Exception:
            lines.append("\n**Row count:** (unable to determine)")

        # Sample rows
        try:
            sample_cursor = conn.execute(
                f"SELECT * FROM [{table_name}] LIMIT 3"
            )
            sample_rows = sample_cursor.fetchall()
            if sample_rows:
                sample_cols = [d[0] for d in sample_cursor.description]
                lines.append("\n**Sample rows (3):**\n")
                lines.append(_rows_to_markdown(sample_rows, sample_cols))
        except Exception:
            pass

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool 3 — get_catalog_summary
# ---------------------------------------------------------------------------

def get_catalog_summary() -> str:
    """
    Return a bird's-eye summary of the catalog database: total documents,
    total products, companies, folders, and product categories.
    """
    conn = _conn()
    try:
        # Total documents
        total_docs = conn.execute(
            "SELECT COUNT(*) as cnt FROM documents"
        ).fetchone()["cnt"]

        # Companies
        companies = conn.execute(
            "SELECT DISTINCT company FROM documents "
            "WHERE company IS NOT NULL AND company != '' "
            "ORDER BY company"
        ).fetchall()
        company_list = [r["company"] for r in companies]

        # Folders
        folders = conn.execute(
            "SELECT folder, COUNT(*) as cnt FROM documents "
            "GROUP BY folder ORDER BY folder"
        ).fetchall()

        # Image types
        image_types = conn.execute(
            "SELECT image_type, COUNT(*) as cnt FROM documents "
            "GROUP BY image_type ORDER BY cnt DESC"
        ).fetchall()

        # Products — parse JSON and count / collect categories
        product_rows = conn.execute(
            "SELECT products FROM documents "
            "WHERE products IS NOT NULL AND products != '[]' AND products != ''"
        ).fetchall()

        total_products = 0
        categories: set = set()

        for row in product_rows:
            raw = row["products"]
            if not raw:
                continue
            try:
                items = json.loads(raw)
                if isinstance(items, list):
                    total_products += len(items)
                    for item in items:
                        cat = None
                        if isinstance(item, dict):
                            cat = (
                                item.get("category")
                                or item.get("product_category")
                                or item.get("type")
                            )
                        if cat and isinstance(cat, str) and cat.strip():
                            categories.add(cat.strip())
            except (json.JSONDecodeError, TypeError):
                pass

        # Products table count (normalized)
        try:
            products_table_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM products"
            ).fetchone()["cnt"]
        except Exception:
            products_table_count = 0

        # Contacts table count (normalized)
        try:
            contacts_table_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM contacts"
            ).fetchone()["cnt"]
        except Exception:
            contacts_table_count = 0

        # Contacts with phone numbers
        try:
            contacts_with_phone = conn.execute(
                "SELECT COUNT(*) as cnt FROM contacts WHERE phone IS NOT NULL AND phone != ''"
            ).fetchone()["cnt"]
        except Exception:
            contacts_with_phone = 0

        # Documents with GPS data
        try:
            docs_with_gps = conn.execute(
                "SELECT COUNT(*) as cnt FROM documents WHERE gps_lat IS NOT NULL"
            ).fetchone()["cnt"]
        except Exception:
            docs_with_gps = 0

        # Documents with date_taken
        try:
            docs_with_date = conn.execute(
                "SELECT COUNT(*) as cnt FROM documents WHERE date_taken IS NOT NULL AND date_taken != ''"
            ).fetchone()["cnt"]
        except Exception:
            docs_with_date = 0

        # Build the summary
        lines = [
            "## KONTACT Catalog Summary\n",
            f"- **Total documents (pages):** {total_docs:,}",
            f"- **Total products extracted:** {total_products:,}",
            f"- **Products table (normalized):** {products_table_count:,}",
            f"- **Contacts table (normalized):** {contacts_table_count:,}",
            f"- **Contacts with phone numbers:** {contacts_with_phone:,}",
            f"- **Documents with GPS data:** {docs_with_gps:,}",
            f"- **Documents with date_taken:** {docs_with_date:,}",
            f"- **Companies:** {len(company_list)}",
        ]

        if company_list:
            lines.append("  - " + ", ".join(company_list))

        lines.append(f"- **Folders:** {len(folders)}")
        for f in folders:
            lines.append(f"  - `{f['folder']}` — {f['cnt']} doc(s)")

        if image_types:
            lines.append(f"- **Image types:**")
            for it in image_types:
                t = it["image_type"] or "(unclassified)"
                lines.append(f"  - {t}: {it['cnt']}")

        if categories:
            sorted_cats = sorted(categories)
            lines.append(f"- **Product categories:** {len(sorted_cats)}")
            lines.append("  - " + ", ".join(sorted_cats))
        else:
            lines.append("- **Product categories:** _(none extracted)_")

        # Queue snapshot
        try:
            q_status = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM queue GROUP BY status"
            ).fetchall()
            if q_status:
                lines.append("\n### Processing Queue")
                for qs in q_status:
                    lines.append(f"  - {qs['status']}: {qs['cnt']}")
        except Exception:
            pass

        return "\n".join(lines)

    except Exception as e:
        return f"Error building summary: {e}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool dispatcher (for agent integration)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tool 4 — open_messenger
# ---------------------------------------------------------------------------

_SUPPORTED_PLATFORMS = {
    "whatsapp", "viber", "telegram", "line", "signal", "wechat", "zalo",
}


def _strip_plus(num: str) -> str:
    return re.sub(r"[^\d]", "", num or "")


def open_messenger(contact_uuid: str, platform: str) -> str:
    """
    Build a clickable deeplink for the given contact + platform.
    Returns the URL plus a markdown render.
    """
    platform = (platform or "").strip().lower()
    if platform not in _SUPPORTED_PLATFORMS:
        return (
            f"Error: Unsupported platform `{platform}`. "
            f"Choose one of: {', '.join(sorted(_SUPPORTED_PLATFORMS))}."
        )

    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM contacts WHERE uuid = ?", (contact_uuid,)
        ).fetchone()
        if not row:
            return f"Error: Contact `{contact_uuid}` not found."

        keys = row.keys()

        def field(name: str):
            return row[name] if name in keys else None

        company = field("company") or ""
        person = field("person") or ""
        label = f"{person or company} ({platform})".strip()

        link = None
        if platform == "whatsapp":
            val = field("whatsapp") or field("phone_e164") or field("phone")
            if not val:
                return "Error: whatsapp not stored for this contact."
            link = f"https://wa.me/{_strip_plus(val)}"
        elif platform == "telegram":
            val = field("telegram")
            if not val:
                return "Error: telegram not stored for this contact."
            v = val.lstrip("@")
            link = f"https://t.me/{v}"
        elif platform == "line":
            val = field("line_id") or field("line")
            if not val:
                return "Error: line not stored for this contact."
            link = f"https://line.me/ti/p/~{val}"
        elif platform == "wechat":
            val = field("wechat_qr_url")
            if not val:
                wid = field("wechat_id")
                if wid:
                    return (
                        f"WeChat ID: `{wid}` (no QR stored — add in WeChat: "
                        f"Add Friend → Search by WeChat ID)\n\n"
                        f"**Contact:** {label}"
                    )
                return "Error: wechat not stored for this contact."
            link = val
        elif platform == "viber":
            val = field("phone_e164") or field("phone")
            if not val:
                return "Error: viber not stored for this contact."
            link = f"viber://add?number={_strip_plus(val)}"
        elif platform == "signal":
            val = field("signal_phone") or field("phone_e164") or field("phone")
            if not val:
                return "Error: signal not stored for this contact."
            link = f"https://signal.me/#p/+{_strip_plus(val)}"
        elif platform == "zalo":
            val = field("phone_e164") or field("phone")
            if not val:
                return "Error: zalo not stored for this contact."
            link = f"https://zalo.me/{_strip_plus(val)}"

        return (
            f"**Open {platform} for {label}**\n\n"
            f"[{link}]({link})\n\n"
            f"`{link}`"
        )

    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool 5 — fetch_catalog_url
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def fetch_catalog_url(url: str) -> str:
    """
    GET a URL with a browser UA. Returns content-type, size, and first
    2000 chars of stripped text (PDFs return metadata only). Read-only.
    """
    if not url or not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            r = client.get(url, headers=headers)
            ctype = r.headers.get("content-type", "unknown")
            size = len(r.content)
            lines = [
                f"**URL:** {url}",
                f"**Status:** {r.status_code}",
                f"**Content-Type:** {ctype}",
                f"**Size:** {size:,} bytes",
            ]
            if "pdf" in ctype.lower() or url.lower().endswith(".pdf"):
                lines.append("\n_(PDF — metadata only, body not extracted.)_")
                return "\n".join(lines)

            try:
                text = r.text
            except Exception:
                return "\n".join(lines) + "\n\n_(Binary body, not text.)_"

            stripped = _HTML_TAG_RE.sub(" ", text)
            stripped = _WS_RE.sub(" ", stripped).strip()
            lines.append("\n**Preview (first 2000 chars):**\n")
            lines.append(stripped[:2000])
            return "\n".join(lines)
    except httpx.TimeoutException:
        return f"Error: Timeout fetching {url}"
    except Exception as e:
        return f"Error fetching URL: {e}"


# ---------------------------------------------------------------------------
# Tool 6 — find_unmapped_wechat_chats
# ---------------------------------------------------------------------------

def find_unmapped_wechat_chats() -> str:
    """List wechat_chat_map rows with no vendor_company assigned."""
    conn = _conn()
    try:
        try:
            cursor = conn.execute(
                "SELECT * FROM wechat_chat_map WHERE vendor_company IS NULL"
            )
        except sqlite3.OperationalError as e:
            return f"Error: {e} (is `wechat_chat_map` table present?)"
        rows = cursor.fetchall()
        if not rows:
            return "_All WeChat chats are mapped to a vendor._"
        columns = [d[0] for d in cursor.description]
        return _rows_to_markdown(rows, columns)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool 7 — list_messenger_contacts
# ---------------------------------------------------------------------------

_PLATFORM_COLUMN = {
    "whatsapp": "whatsapp",
    "viber": "phone_e164",   # viber keyed off phone_e164
    "telegram": "telegram",
    "line": "line_id",
    "wechat": "wechat_id",
    "signal": "signal_phone",
    "zalo": "phone_e164",
}


def list_messenger_contacts(platform: str) -> str:
    """List contacts that have a stored handle for the given platform."""
    platform = (platform or "").strip().lower()
    col = _PLATFORM_COLUMN.get(platform)
    if not col:
        return (
            f"Error: Unsupported platform `{platform}`. "
            f"Choose one of: {', '.join(sorted(_PLATFORM_COLUMN))}."
        )
    conn = _conn()
    try:
        try:
            cursor = conn.execute(
                f"SELECT company, person, {col} FROM contacts "
                f"WHERE {col} IS NOT NULL AND {col} != '' "
                f"ORDER BY company LIMIT 200"
            )
        except sqlite3.OperationalError as e:
            return f"Error: {e} (is column `{col}` present on contacts?)"
        rows = cursor.fetchall()
        if not rows:
            return f"_No contacts with `{platform}` ({col}) stored._"
        columns = [d[0] for d in cursor.description]
        return _rows_to_markdown(rows, columns)
    finally:
        conn.close()


def semantic_search_images(query: str, limit: int = 8, user: dict = None) -> str:
    """Find catalog images by semantic content.

    Uses ChromaDB vector store. Returns markdown w/ [IMAGE: folder/file]
    citations the frontend renders as clickable thumbs. Per-user scoped via
    document join — admin sees all.

    Args:
        query: free-text search ("red shoes", "industrial pumps", "wechat qr").
        limit: max results (default 8, max 20).
        user: current user dict (injected by execute_tool).
    """
    import vectorstore as _vs
    import database as _db

    if not query or not query.strip():
        return "_Empty query._"
    limit = max(1, min(int(limit or 8), 20))
    try:
        hits = _vs.query(query.strip(), n_results=limit * 2)  # over-fetch then filter
    except Exception as e:
        return f"_Vector search error: {e}_"
    if not hits:
        return "_No semantic matches._"

    # Gather folder/file pairs to look up doc + owner
    folder_files = []
    for h in hits:
        meta = h.get("metadata") or {}
        folder = meta.get("folder")
        fname = meta.get("source_file") or meta.get("file")
        if folder and fname:
            folder_files.append((folder, fname))
    if not folder_files:
        return "_Matches lack folder/file metadata._"

    is_admin = (user or {}).get("role") in ("super_admin", "admin")
    user_uuid = (user or {}).get("uuid")

    conn = _db._conn()
    try:
        placeholders = ",".join(["(?, ?)"] * len(folder_files))
        flat = [v for pair in folder_files for v in pair]
        if is_admin:
            rows = conn.execute(
                f"SELECT folder, source_file, company, title, image_type, trade_show "
                f"FROM documents WHERE (folder, source_file) IN (VALUES {placeholders})",
                flat,
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT folder, source_file, company, title, image_type, trade_show "
                f"FROM documents WHERE (folder, source_file) IN (VALUES {placeholders}) "
                f"AND owner_uuid = ?",
                flat + [user_uuid],
            ).fetchall()
    finally:
        conn.close()

    # Build markdown ordered by original semantic hit order
    by_key = {(r["folder"], r["source_file"]): dict(r) for r in rows}
    lines = ["**Image matches:**", ""]
    seen = set()
    shown = 0
    for folder, fname in folder_files:
        if (folder, fname) in seen:
            continue
        seen.add((folder, fname))
        d = by_key.get((folder, fname))
        if not d:
            continue  # filtered out by ownership
        bits = []
        if d.get("company"): bits.append(d["company"])
        if d.get("title"): bits.append(d["title"])
        if d.get("image_type"): bits.append(f"`{d['image_type']}`")
        if d.get("trade_show"): bits.append(f"@ {d['trade_show']}")
        desc = " · ".join(bits) or fname
        lines.append(f"- {desc}  [IMAGE: {folder}/{fname}]")
        shown += 1
        if shown >= limit:
            break

    if shown == 0:
        return "_No matches visible to your account._"
    return "\n".join(lines)


TOOLS = {
    "query_catalog_db": query_catalog_db,
    "introspect_schema": introspect_schema,
    "get_catalog_summary": get_catalog_summary,
    "semantic_search_images": semantic_search_images,
    "open_messenger": open_messenger,
    "fetch_catalog_url": fetch_catalog_url,
    "find_unmapped_wechat_chats": find_unmapped_wechat_chats,
    "list_messenger_contacts": list_messenger_contacts,
}


def execute_tool(name: str, args: dict, user: dict = None) -> str:
    """Dispatch a tool call by name. Returns a string result.

    `user` is forwarded to tools that accept a `user` kwarg (e.g. query_catalog_db)
    so tenancy can be enforced.
    """
    fn = TOOLS.get(name)
    if not fn:
        return f"Error: Unknown tool `{name}`."
    try:
        # Inject user into tools that accept it
        if name in ("query_catalog_db", "semantic_search_images"):
            return fn(user=user, **args)
        return fn(**args)
    except Exception as e:
        return f"Error executing {name}: {e}"
