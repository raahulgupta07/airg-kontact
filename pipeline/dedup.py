"""Dedup scanner. Inserts merge_proposals (pending) for human approval.

Tiers (confidence ranked):

Contacts:
  A. phone_e164 collision           0.99
  B. email collision (lower+trim)   0.95
  C. company+person fuzzy match     0.80

Documents:
  D. file_hash collision (exact)    0.99
  E. image_phash hamming <= 4       0.95
  F. (source_file, owner_uuid) dup  0.75   <- "same filename re-upload"
  G. image_phash hamming 5-8        0.60

Keep = oldest id (lower). Drop = newer (typically duplicate re-upload).
Skips blacklisted pairs + already-pending/approved pairs.
"""
from __future__ import annotations

import logging

import database as db

log = logging.getLogger("kontact.dedup")


def _snapshot_contact(uuid: str) -> dict:
    c = db._conn()
    try:
        row = c.execute("SELECT * FROM contacts WHERE uuid = ?", (uuid,)).fetchone()
        return dict(row) if row else {}
    finally:
        c.close()


def _snapshot_document(uuid: str) -> dict:
    c = db._conn()
    try:
        row = c.execute("SELECT * FROM documents WHERE uuid = ?", (uuid,)).fetchone()
        return dict(row) if row else {}
    finally:
        c.close()


def _hamming(a: str, b: str) -> int:
    """Hex-string Hamming distance (bit-level)."""
    if not a or not b or len(a) != len(b):
        return 999
    try:
        ai = int(a, 16)
        bi = int(b, 16)
        return bin(ai ^ bi).count("1")
    except Exception:
        return 999


def scan_contacts() -> dict:
    """Tiers A/B/C → propose contact merges."""
    proposed = {"phone_e164": 0, "email": 0, "company_person": 0}
    c = db._conn()
    try:
        # Tier A: phone_e164 collision
        a_groups = c.execute(
            """
            SELECT phone_e164, GROUP_CONCAT(uuid, '|') AS uuids
            FROM contacts
            WHERE phone_e164 IS NOT NULL AND TRIM(phone_e164) != ''
            GROUP BY phone_e164
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        # Tier B: email collision
        b_groups = c.execute(
            """
            SELECT LOWER(TRIM(email)) AS norm_email, GROUP_CONCAT(uuid, '|') AS uuids
            FROM contacts
            WHERE email IS NOT NULL AND TRIM(email) != ''
            GROUP BY LOWER(TRIM(email))
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        # Tier C: company+person fuzzy
        c_groups = c.execute(
            """
            SELECT LOWER(TRIM(company)) || '|' || LOWER(TRIM(person)) AS key,
                   GROUP_CONCAT(uuid, '|') AS uuids
            FROM contacts
            WHERE company IS NOT NULL AND TRIM(company) != ''
              AND person IS NOT NULL AND TRIM(person) != ''
            GROUP BY LOWER(TRIM(company)), LOWER(TRIM(person))
            HAVING COUNT(*) > 1
            """
        ).fetchall()
    finally:
        c.close()

    def _propose_group(uuids_csv: str, reason: str, confidence: float, counter_key: str):
        uuids = [u for u in (uuids_csv or "").split("|") if u]
        if len(uuids) < 2:
            return
        # Keep first (lowest id by GROUP_CONCAT order is undefined; query oldest explicitly)
        c2 = db._conn()
        try:
            order = c2.execute(
                f"SELECT uuid FROM contacts WHERE uuid IN ({','.join('?' * len(uuids))}) ORDER BY id ASC",
                uuids,
            ).fetchall()
            ordered = [r["uuid"] for r in order]
        finally:
            c2.close()
        if len(ordered) < 2:
            return
        keep = ordered[0]
        for drop in ordered[1:]:
            snap = _snapshot_contact(drop)
            pid = db.merge_proposal_create(
                entity_type="contact",
                keep_uuid=keep, drop_uuid=drop,
                match_reason=reason, confidence=confidence,
                before_snapshot=snap,
            )
            if pid:
                proposed[counter_key] = proposed.get(counter_key, 0) + 1

    for g in a_groups:
        _propose_group(g["uuids"], "phone_e164", 0.99, "phone_e164")
    for g in b_groups:
        _propose_group(g["uuids"], "email", 0.95, "email")
    for g in c_groups:
        _propose_group(g["uuids"], "company_person", 0.80, "company_person")

    return proposed


def scan_documents() -> dict:
    """Tiers D/E/F/G → propose document merges."""
    proposed = {"file_hash": 0, "phash_exact": 0, "filename": 0, "phash_near": 0}

    c = db._conn()
    try:
        # Tier D: file_hash collision
        d_groups = c.execute(
            """
            SELECT file_hash, GROUP_CONCAT(uuid, '|') AS uuids
            FROM documents
            WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''
            GROUP BY file_hash
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        # Tier F: same source_file + owner_uuid (re-upload pattern)
        f_groups = c.execute(
            """
            SELECT source_file, owner_uuid, GROUP_CONCAT(uuid, '|') AS uuids
            FROM documents
            WHERE source_file IS NOT NULL AND TRIM(source_file) != ''
            GROUP BY source_file, owner_uuid
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        # Tier E/G: phash hamming pairwise (only for blurry/clear, capped)
        phash_rows = c.execute(
            "SELECT uuid, image_phash FROM documents "
            "WHERE image_phash IS NOT NULL AND TRIM(image_phash) != '' "
            "ORDER BY id ASC LIMIT 5000"
        ).fetchall()
    finally:
        c.close()

    def _propose_doc(uuids_csv: str, reason: str, confidence: float, counter_key: str):
        uuids = [u for u in (uuids_csv or "").split("|") if u]
        if len(uuids) < 2:
            return
        c2 = db._conn()
        try:
            order = c2.execute(
                f"SELECT uuid FROM documents WHERE uuid IN ({','.join('?' * len(uuids))}) ORDER BY id ASC",
                uuids,
            ).fetchall()
            ordered = [r["uuid"] for r in order]
        finally:
            c2.close()
        if len(ordered) < 2:
            return
        keep = ordered[0]
        for drop in ordered[1:]:
            snap = _snapshot_document(drop)
            pid = db.merge_proposal_create(
                entity_type="document",
                keep_uuid=keep, drop_uuid=drop,
                match_reason=reason, confidence=confidence,
                before_snapshot=snap,
            )
            if pid:
                proposed[counter_key] = proposed.get(counter_key, 0) + 1

    for g in d_groups:
        _propose_doc(g["uuids"], "file_hash", 0.99, "file_hash")
    for g in f_groups:
        _propose_doc(g["uuids"], "filename", 0.75, "filename")

    # Pairwise phash (O(N^2/2) — capped 5000 = 12.5M pairs worst case; fast in C)
    rows = [(r["uuid"], r["image_phash"]) for r in phash_rows]
    n = len(rows)
    for i in range(n):
        u_a, p_a = rows[i]
        for j in range(i + 1, n):
            u_b, p_b = rows[j]
            dist = _hamming(p_a, p_b)
            if dist == 0:
                continue  # exact handled by file_hash already mostly
            if dist <= 4:
                keep, drop = sorted([u_a, u_b])
                snap = _snapshot_document(drop)
                pid = db.merge_proposal_create(
                    entity_type="document",
                    keep_uuid=keep, drop_uuid=drop,
                    match_reason="phash_exact", confidence=0.95,
                    before_snapshot=snap,
                )
                if pid:
                    proposed["phash_exact"] += 1
            elif dist <= 8:
                keep, drop = sorted([u_a, u_b])
                snap = _snapshot_document(drop)
                pid = db.merge_proposal_create(
                    entity_type="document",
                    keep_uuid=keep, drop_uuid=drop,
                    match_reason="phash_near", confidence=0.60,
                    before_snapshot=snap,
                )
                if pid:
                    proposed["phash_near"] += 1

    return proposed


def scan_all() -> dict:
    """Run both scanners. Returns combined report."""
    return {
        "contacts": scan_contacts(),
        "documents": scan_documents(),
    }
