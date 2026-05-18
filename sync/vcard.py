"""vCard (RFC 6350 / VERSION:3.0) generation utilities."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Iterable


def _esc(value) -> str:
    """Escape a value for inclusion in a vCard field (RFC 6350 §3.4)."""
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "")
    s = s.replace(",", "\\,").replace(";", "\\;")
    return s


def _fold(line: str, width: int = 75) -> str:
    if len(line) <= width:
        return line
    chunks = [line[:width]]
    rest = line[width:]
    while rest:
        chunks.append(" " + rest[: width - 1])
        rest = rest[width - 1 :]
    return "\r\n".join(chunks)


def to_vcard(contact: dict) -> str:
    """Build a single VCARD 3.0 string for a contact dict."""
    c = contact or {}
    person = c.get("person") or c.get("name") or c.get("company") or "Contact"
    company = c.get("company") or ""
    phone = c.get("phone_e164") or c.get("phone") or ""
    email = c.get("email") or ""
    website = c.get("website") or ""
    address = c.get("address") or ""

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        _fold(f"FN:{_esc(person)}"),
    ]
    if company:
        lines.append(_fold(f"ORG:{_esc(company)}"))
    if phone:
        lines.append(_fold(f"TEL;TYPE=CELL:{_esc(phone)}"))
    if email:
        lines.append(_fold(f"EMAIL:{_esc(email)}"))
    if website:
        lines.append(_fold(f"URL:{_esc(website)}"))
    if address:
        # Single street component fallback; ADR is structured (PO;ext;street;city;region;postal;country)
        lines.append(_fold(f"ADR;TYPE=WORK:;;{_esc(address)};;;;"))

    messenger_map = [
        ("whatsapp", "X-WHATSAPP"),
        ("viber", "X-VIBER"),
        ("telegram", "X-TELEGRAM"),
        ("line_id", "X-LINE"),
        ("wechat_id", "X-WECHAT"),
        ("signal_phone", "X-SIGNAL"),
    ]
    for key, tag in messenger_map:
        val = c.get(key)
        if val:
            lines.append(_fold(f"{tag}:{_esc(val)}"))

    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def _safe_filename(name: str, default: str = "contact") -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    s = s.strip("._-") or default
    return s[:80]


def bulk_vcards_zip(contacts: Iterable[dict]) -> bytes:
    """Return an in-memory ZIP containing one .vcf file per contact."""
    buf = io.BytesIO()
    used = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in contacts:
            base = c.get("person") or c.get("company") or c.get("uuid") or "contact"
            fname = _safe_filename(base) + ".vcf"
            used[fname] = used.get(fname, 0) + 1
            if used[fname] > 1:
                root, ext = fname.rsplit(".", 1)
                fname = f"{root}_{used[fname]}.{ext}"
            zf.writestr(fname, to_vcard(c).encode("utf-8"))
    return buf.getvalue()
