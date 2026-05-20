"""Backfill missing company names on existing contacts.

Cascade per row (stops at first non-empty source):
  1. documents.company (JOIN on document_uuid)
  2. products.company first non-empty (JOIN on document_uuid)
  3. URL resolver retry on contacts.website (if cheap_only=False)
  4. Website domain heuristic
  5. Email domain heuristic (skip generic providers)

LLM re-vision step is in backfill_company_llm (separate fn, cost-gated).

Skips rows with edit_count > 0 (user-edited = sacred).
Logs each fix to audit_events with method=step_N.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import database as db
from pipeline.company_resolver import (
    company_from_domain,
    company_from_email,
)

log = logging.getLogger("kontact.backfill")


def _fetch_blank_company_rows(limit: int = 1000) -> list[dict]:
    """Contacts where company empty AND not user-edited."""
    c = db._conn()
    try:
        rows = c.execute(
            """
            SELECT c.uuid, c.document_uuid, c.document_id, c.website, c.email, c.owner_uuid
            FROM contacts c
            WHERE (c.company IS NULL OR TRIM(c.company) = '')
              AND COALESCE(c.edit_count, 0) = 0
            ORDER BY c.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def _doc_company(document_uuid: str) -> str:
    if not document_uuid:
        return ""
    c = db._conn()
    try:
        row = c.execute(
            "SELECT company FROM documents WHERE uuid = ? LIMIT 1",
            (document_uuid,),
        ).fetchone()
        return (row["company"] or "").strip() if row else ""
    finally:
        c.close()


def _product_company(document_uuid: str) -> str:
    if not document_uuid:
        return ""
    c = db._conn()
    try:
        row = c.execute(
            "SELECT company FROM products WHERE document_uuid = ? "
            "AND company IS NOT NULL AND TRIM(company) != '' LIMIT 1",
            (document_uuid,),
        ).fetchone()
        return (row["company"] or "").strip() if row else ""
    finally:
        c.close()


def _apply_update(contact_uuid: str, company: str, method: str, owner_uuid: Optional[str]):
    with db.write_lock():
        _apply_update_locked(contact_uuid, company, method, owner_uuid)


def _apply_update_locked(contact_uuid: str, company: str, method: str, owner_uuid: Optional[str]):
    c = db._conn()
    try:
        c.execute(
            "UPDATE contacts SET company = ?, backfill_source = ?, updated_at = ? "
            "WHERE uuid = ? AND (company IS NULL OR TRIM(company) = '')",
            (company, method, db._now_iso(), contact_uuid),
        )
        try:
            db.log_event(
                c,
                event_type="backfill_company",
                entity_type="contact",
                entity_uuid=contact_uuid,
                user_uuid=owner_uuid,
                detail={"method": method, "value": company},
            )
        except Exception:
            pass
        c.commit()
    finally:
        c.close()


async def _try_url_resolver(website: str) -> str:
    """Re-fetch website + try JSON-LD/OG/title for company name."""
    if not website:
        return ""
    try:
        from pipeline.url_resolver import resolve_profile_url
        resolved = await resolve_profile_url(website)
        if resolved and resolved.get("company"):
            return str(resolved["company"]).strip()
    except Exception as e:
        log.debug("backfill url resolver failed for %s: %s", website, e)
    return ""


async def backfill_company(
    limit: int = 1000,
    cheap_only: bool = True,
    dry_run: bool = False,
) -> dict:
    """Run cascade. Returns {scanned, fixed_by_step, errors}.

    cheap_only=True skips URL resolver (HTTP cost).
    dry_run=True logs but does not write.
    """
    rows = _fetch_blank_company_rows(limit=limit)
    fixed_by_step = {"doc": 0, "product": 0, "url": 0, "domain": 0, "email": 0}
    errors: list[str] = []

    for r in rows:
        contact_uuid = r["uuid"]
        document_uuid = r.get("document_uuid")
        website = (r.get("website") or "").strip()
        email = (r.get("email") or "").strip()
        owner_uuid = r.get("owner_uuid")

        company = ""
        method = ""

        # Step 1: doc.company
        company = _doc_company(document_uuid)
        if company:
            method = "doc"

        # Step 2: products[0].company
        if not company:
            company = _product_company(document_uuid)
            if company:
                method = "product"

        # Step 3: URL resolver (cheap_only skips)
        if not company and website and not cheap_only:
            try:
                company = await _try_url_resolver(website)
                if company:
                    method = "url"
            except Exception as e:
                errors.append(f"{contact_uuid}: url {e}")

        # Step 4: website domain
        if not company and website:
            g = company_from_domain(website)
            if g:
                company = g
                method = "domain"

        # Step 5: email domain
        if not company and email:
            g = company_from_email(email)
            if g:
                company = g
                method = "email"

        if company:
            fixed_by_step[method] = fixed_by_step.get(method, 0) + 1
            if not dry_run:
                try:
                    _apply_update(contact_uuid, company, method, owner_uuid)
                except Exception as e:
                    errors.append(f"{contact_uuid}: write {e}")

    return {
        "scanned": len(rows),
        "fixed_total": sum(fixed_by_step.values()),
        "fixed_by_step": fixed_by_step,
        "errors": errors[:50],
        "dry_run": dry_run,
        "cheap_only": cheap_only,
    }


async def backfill_company_llm(limit: int = 50) -> dict:
    """LLM re-vision step. Cost-capped. Skips blurry images.

    Re-runs extractor on source images for contacts still blank after cheap cascade.
    """
    c = db._conn()
    try:
        rows = c.execute(
            """
            SELECT c.uuid AS contact_uuid, c.document_uuid, c.owner_uuid,
                   d.folder, d.source_file, d.is_blurry
            FROM contacts c
            JOIN documents d ON c.document_uuid = d.uuid
            WHERE (c.company IS NULL OR TRIM(c.company) = '')
              AND COALESCE(c.edit_count, 0) = 0
              AND COALESCE(d.is_blurry, 0) = 0
              AND d.source_file IS NOT NULL
            ORDER BY c.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        rows = [dict(r) for r in rows]
    finally:
        c.close()

    if not rows:
        return {"scanned": 0, "fixed": 0, "errors": []}

    import httpx, os
    import config as _config
    from pipeline.extractor import extract_one
    from pipeline.loader import load_image

    fixed = 0
    errors: list[str] = []

    sem = asyncio.Semaphore(2)
    async with httpx.AsyncClient(timeout=120) as client:
        for r in rows:
            folder = r["folder"]
            source = r["source_file"]
            path = os.path.join(_config.UPLOADS_DIR, folder, source)
            if not os.path.isfile(path):
                continue
            try:
                img = load_image(path)
                if not img:
                    continue
                data = await extract_one(client, img, sem)
                company = (data.get("company") or "").strip()
                if not company:
                    contact = data.get("contact") or {}
                    if isinstance(contact, dict):
                        company = (contact.get("company") or "").strip()
                if company:
                    _apply_update(r["contact_uuid"], company, "llm_revision", r.get("owner_uuid"))
                    fixed += 1
            except Exception as e:
                errors.append(f"{r['contact_uuid']}: {e}")

    return {"scanned": len(rows), "fixed": fixed, "errors": errors[:20]}
