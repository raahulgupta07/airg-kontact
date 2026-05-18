"""Heuristic auto-tagger — derives 3-6 tags from extracted record content.

Pure-Python: no LLM call (extractor already burned tokens; this is free).
Categories: industry, region, contact-type, signal flags.
"""
from __future__ import annotations

import re
from typing import Iterable

# Coarse industry keyword sets
_INDUSTRY: list[tuple[str, list[str]]] = [
    ("pumps",         ["pump", "centrifugal", "diaphragm", "hydraulic"]),
    ("electronics",   ["led", "lcd", "pcb", "semiconductor", "sensor"]),
    ("machinery",     ["machine", "cnc", "lathe", "press", "mill"]),
    ("textile",       ["fabric", "yarn", "loom", "garment"]),
    ("food",          ["food", "beverage", "snack", "spice", "tea", "coffee"]),
    ("pharma",        ["pharma", "medicine", "drug", "tablet", "capsule"]),
    ("packaging",     ["packaging", "carton", "bottle", "label"]),
    ("auto",          ["automotive", "vehicle", "engine", "tire", "spare"]),
    ("chemicals",     ["chemical", "polymer", "resin", "solvent"]),
    ("solar",         ["solar", "pv", "photovoltaic", "panel"]),
    ("logistics",     ["shipping", "forwarder", "freight", "logistics"]),
]


def _country_to_region(country: str) -> str | None:
    if not country:
        return None
    c = country.strip()
    asian = {"中国", "China", "Japan", "Korea", "Vietnam", "Thailand",
             "Indonesia", "Malaysia", "Singapore", "India", "Taiwan"}
    eu = {"Germany", "France", "Italy", "Spain", "Netherlands", "Belgium",
          "Poland", "Czech", "Austria", "Switzerland", "Sweden", "Denmark"}
    na = {"United States", "USA", "Canada", "Mexico"}
    if c in asian or any(c.startswith(x) for x in ("中", "日", "韩", "印")):
        return "region-asia"
    if c in eu:
        return "region-eu"
    if c in na:
        return "region-na"
    return None


def suggest_tags(record: dict) -> list[str]:
    tags: list[str] = []
    meta = record.get("metadata") or {}
    raw = " ".join([
        record.get("title", "") or "",
        record.get("company", "") or "",
        record.get("raw_text", "") or "",
    ]).lower()

    # Image type -> coarse content tag
    img_type = (record.get("image_type") or "").lower()
    if img_type in ("qr_card", "business_card"):
        tags.append("contact-card")
    elif img_type == "product_page":
        tags.append("product")
    elif img_type == "price_list":
        tags.append("pricing")
    elif img_type == "blurry":
        tags.append("blurry")

    # Industry by keywords
    for tag, kws in _INDUSTRY:
        if any(kw in raw for kw in kws):
            tags.append(tag)
            break

    # Geo
    region = _country_to_region(meta.get("country"))
    if region:
        tags.append(region)
    elif meta.get("country"):
        tags.append(f"country:{meta['country']}")

    # Signal flags
    if record.get("qr_payloads"):
        tags.append("has-qr")
    contact = record.get("contact") or {}
    if any(contact.get(k) for k in ("whatsapp", "wechat_qr_url", "telegram", "line_id")):
        tags.append("has-messenger")
    if contact.get("phone") or contact.get("phone_e164"):
        tags.append("has-phone")
    if contact.get("email"):
        tags.append("has-email")

    # Pricing signal
    if any(re.search(r"\$|€|¥|£|USD|EUR|JPY|RMB|CNY", str(p.get("price", "")))
           for p in (record.get("products") or []) if isinstance(p, dict)):
        tags.append("has-pricing")

    # Dedupe + cap
    seen = set()
    out = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:6]
