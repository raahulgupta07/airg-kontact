"""Cascading company-name resolver.

Stops at first non-empty source. Used at insert time (database.insert_extraction)
and at backfill time (pipeline.backfill.backfill_company).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Generic email providers — domain is NOT the company name.
_GENERIC_EMAIL_DOMAINS = {
    "gmail", "googlemail", "yahoo", "ymail", "rocketmail",
    "hotmail", "outlook", "live", "msn", "passport",
    "icloud", "me", "mac",
    "aol", "compuserve",
    "protonmail", "proton", "pm",
    "mail", "email", "inbox",
    "zoho", "yandex", "ya",
    "gmx", "web", "t-online",
    "qq", "163", "126", "yeah", "sina", "sohu", "foxmail", "tom", "21cn",
    "naver", "daum", "hanmail", "kakao",
    "rediffmail", "rediff",
    "fastmail",
}

# Generic web hosts that aren't a company.
_GENERIC_WEB_HOSTS = {
    "google", "bing", "duckduckgo",
    "facebook", "fb", "instagram", "twitter", "x",
    "linkedin", "youtube", "tiktok", "wechat", "weibo",
    "github", "gitlab", "bitbucket",
    "wa", "telegram", "t",
    "wordpress", "wix", "squarespace", "weebly", "blogspot",
    "shopify", "etsy", "amazon", "ebay", "aliexpress", "alibaba",
}


def _titlecase_brand(raw: str) -> str:
    """`fusion-sol` → `Fusion Sol`, `acmecorp` → `Acmecorp`."""
    if not raw:
        return ""
    cleaned = re.sub(r"[._-]+", " ", raw).strip()
    if not cleaned:
        return ""
    return " ".join(w.capitalize() for w in cleaned.split())


def _registrable(host: str) -> str | None:
    """Return left-most label of registrable domain (best-effort, no tldextract dep).

    `www.fusionsol.com` → `fusionsol`
    `acme.co.uk` → `acme`
    `shop.acme-tech.com` → `acme-tech`
    """
    if not host:
        return None
    host = host.lower().strip().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) < 2:
        return None
    # Two-label ccTLDs (.co.uk, .com.mm, .com.cn, .co.jp, .com.au …)
    _CC_2LABEL = {
        "co", "com", "net", "org", "gov", "edu", "ac",
    }
    if len(parts) >= 3 and parts[-2] in _CC_2LABEL and len(parts[-1]) == 2:
        candidate = parts[-3]
    else:
        candidate = parts[-2]
    if not candidate or len(candidate) < 3 or candidate.isdigit():
        return None
    return candidate


def company_from_domain(host_or_url: str) -> str | None:
    """`https://www.fusionsol.com/contact` → `Fusionsol`. Returns None for generic hosts."""
    if not host_or_url:
        return None
    raw = host_or_url.strip()
    if "//" not in raw:
        raw = "http://" + raw
    try:
        host = urlparse(raw).hostname or ""
    except Exception:
        return None
    reg = _registrable(host)
    if not reg:
        return None
    if reg in _GENERIC_WEB_HOSTS:
        return None
    return _titlecase_brand(reg)


def company_from_email(email: str) -> str | None:
    """`john@fusionsol.com` → `Fusionsol`. Skips gmail/yahoo/qq/etc."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    if not domain:
        return None
    reg = _registrable(domain)
    if not reg:
        return None
    if reg in _GENERIC_EMAIL_DOMAINS:
        return None
    return _titlecase_brand(reg)


def resolve_company(
    contact: dict | None = None,
    doc_company: str = "",
    products: list | None = None,
    website: str = "",
    email: str = "",
) -> str:
    """Cascade resolver. Stops at first non-empty.

    Order:
      1. contact.company (LLM/vCard extract)
      2. doc-level company (LLM extract)
      3. first product.company
      4. website domain
      5. email domain (skips generic providers)
    Returns "" if all sources empty.
    """
    contact = contact or {}
    products = products or []

    # 1. contact.company
    val = (contact.get("company") or "").strip()
    if val:
        return val

    # 2. doc-level
    val = (doc_company or "").strip()
    if val:
        return val

    # 3. first product
    for p in products:
        if isinstance(p, dict):
            pc = (p.get("company") or "").strip()
            if pc:
                return pc

    # 4. website
    if website:
        guess = company_from_domain(website)
        if guess:
            return guess

    # 5. email
    if email:
        guess = company_from_email(email)
        if guess:
            return guess

    return ""
