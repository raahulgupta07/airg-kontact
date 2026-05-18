"""Resolve a URL (typically from a QR code) into structured contact data.

Pipeline:
 1. SSRF guard (block private/loopback/link-local hosts)
 2. HTTP GET via httpx with browser-like UA, short timeout, redirect cap
 3. Parse HTML: JSON-LD → microdata → OG/Twitter meta → mailto/tel/regex
 4. Return normalized dict — feeds into contact upsert
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from typing import Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger("kontact.pipeline.url_resolver")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

FETCH_TIMEOUT = 8.0
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 4

# Schemes worth fetching; vCard URLs handled separately
_OK_SCHEMES = {"http", "https"}

# Phone — broad, normalized later via phonenumbers
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{6,18}\d")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


# ─── SSRF guard ──────────────────────────────────────────────────────

def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _safe_host(host: str) -> bool:
    """Return True if the host resolves to a non-private public IP."""
    if not host:
        return False
    # Block obvious local hostnames
    lower = host.lower()
    if lower in {"localhost", "ip6-localhost", "ip6-loopback"}:
        return False
    if lower.endswith(".local") or lower.endswith(".internal") or lower.endswith(".lan"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        if _is_private_ip(addr):
            return False
    return True


# ─── extraction helpers ──────────────────────────────────────────────

def _flat(obj):
    """Yield every dict in a nested JSON-LD blob."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _flat(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flat(v)


def _from_jsonld(soup) -> dict:
    out: dict = {}
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.text or ""
        if not text.strip():
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _flat(data):
            t = node.get("@type") or ""
            if isinstance(t, list):
                t = next(iter(t), "")
            if t in ("Person", "Organization", "LocalBusiness", "Restaurant", "Store"):
                if "name" in node and not out.get("name"):
                    out["name"] = str(node["name"]).strip()
                if "telephone" in node and not out.get("phone"):
                    out["phone"] = str(node["telephone"]).strip()
                if "email" in node and not out.get("email"):
                    out["email"] = str(node["email"]).strip().lstrip("mailto:")
                if "jobTitle" in node and not out.get("job_title"):
                    out["job_title"] = str(node["jobTitle"]).strip()
                # Address
                addr = node.get("address")
                if isinstance(addr, dict) and not out.get("address"):
                    parts = [
                        addr.get("streetAddress"),
                        addr.get("addressLocality"),
                        addr.get("addressRegion"),
                        addr.get("postalCode"),
                        addr.get("addressCountry"),
                    ]
                    out["address"] = ", ".join(p for p in parts if p)
                # Organization on a Person
                org = node.get("worksFor") or node.get("affiliation")
                if isinstance(org, dict) and not out.get("company"):
                    out["company"] = org.get("name")
                elif isinstance(org, str) and not out.get("company"):
                    out["company"] = org
                if t in ("Organization", "LocalBusiness", "Restaurant", "Store"):
                    if not out.get("company"):
                        out["company"] = node.get("name")
                # Social handles
                same = node.get("sameAs")
                if isinstance(same, list):
                    out.setdefault("social", []).extend([str(s) for s in same])
                elif isinstance(same, str):
                    out.setdefault("social", []).append(same)
    return out


def _from_meta(soup) -> dict:
    out: dict = {}

    def _m(prop):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        return (tag.get("content") if tag else None) or None

    title = _m("og:title") or _m("twitter:title")
    if title:
        out["name"] = title.strip()
    desc = _m("og:description") or _m("twitter:description") or _m("description")
    if desc:
        out["description"] = desc.strip()
    site = _m("og:site_name")
    if site and not out.get("company"):
        out["company"] = site.strip()
    img = _m("og:image") or _m("twitter:image")
    if img:
        out["image_url"] = img
    return out


def _from_links(soup) -> dict:
    out: dict = {"social": []}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:") and "email" not in out:
            out["email"] = href[7:].split("?")[0].strip()
        elif href.startswith("tel:") and "phone" not in out:
            out["phone"] = href[4:].strip()
        else:
            low = href.lower()
            for host in (
                "linkedin.com", "twitter.com", "x.com", "facebook.com",
                "instagram.com", "youtube.com", "tiktok.com", "github.com",
                "weibo.com",
            ):
                if host in low:
                    out["social"].append(href)
                    break
    if not out["social"]:
        out.pop("social", None)
    return out


def _from_text(html_text: str) -> dict:
    out: dict = {}
    # Strip HTML tags crudely for regex over visible text
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text)
    m = _EMAIL_RE.search(text)
    if m:
        out["email"] = m.group(0)
    m = _PHONE_RE.search(text)
    if m:
        out["phone_text"] = m.group(0)
    return out


def _normalize_phone(raw: str) -> Optional[str]:
    if not raw:
        return None
    try:
        import phonenumbers
    except ImportError:
        return raw
    for region in (None, "US", "CN", "IN", "GB", "DE", "FR"):
        try:
            pn = phonenumbers.parse(raw, region)
            if phonenumbers.is_valid_number(pn):
                return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            continue
    return None


# ─── public API ──────────────────────────────────────────────────────

async def resolve_profile_url(url: str) -> dict:
    """Fetch URL safely and return normalized contact dict.

    Returns {} on any failure (do not raise — best-effort enrichment).
    """
    if not url or not isinstance(url, str):
        return {}
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return {}
    if parsed.scheme not in _OK_SCHEMES:
        return {}
    if not _safe_host(parsed.hostname or ""):
        log.info("url_resolver: unsafe host blocked: %s", parsed.hostname)
        return {}

    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "").lower()
            if "html" not in ctype and "xml" not in ctype:
                return {}
            # Size guard
            body = r.content[:MAX_BYTES]
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        log.info("url_resolver: fetch failed for %s: %s", url, e)
        return {}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    try:
        soup = BeautifulSoup(body, "html.parser")
    except Exception as e:
        log.warning("url_resolver: parse failed: %s", e)
        return {}

    out: dict = {"source_url": url}
    # Highest signal first; later sources only fill gaps
    for fn in (_from_jsonld, _from_meta, _from_links):
        try:
            data = fn(soup)
        except Exception as e:
            log.debug("url_resolver: extractor %s failed: %s", fn.__name__, e)
            continue
        for k, v in data.items():
            if v and not out.get(k):
                out[k] = v
    try:
        text_data = _from_text(body.decode(r.encoding or "utf-8", errors="ignore"))
        for k, v in text_data.items():
            if v and not out.get(k):
                out[k] = v
    except Exception:
        pass

    # Phone normalization (E.164)
    if out.get("phone"):
        e164 = _normalize_phone(out["phone"])
        if e164:
            out["phone_e164"] = e164
    elif out.get("phone_text"):
        e164 = _normalize_phone(out["phone_text"])
        if e164:
            out["phone"] = out["phone_text"]
            out["phone_e164"] = e164

    # Trim social list
    if out.get("social"):
        out["social"] = list(dict.fromkeys(out["social"]))[:10]

    return out
