"""URL snapshot ingest: fetch HTML/PDF and save to disk."""
from __future__ import annotations

import hashlib
import os
import re
from urllib.parse import urlparse

import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


def _slug(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s or "")
    return s.strip("_")[:max_len] or "page"


def snapshot_url(url: str, out_dir: str) -> str:
    """Fetch a URL and save to disk. Returns the saved file path.

    Content-type drives the extension: html, pdf, image/* — otherwise binary.
    """
    os.makedirs(out_dir, exist_ok=True)
    headers = {"User-Agent": UA, "Accept": "*/*"}
    with httpx.Client(follow_redirects=True, timeout=30, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower().split(";")[0].strip()
        body = r.content

    parsed = urlparse(url)
    host = parsed.netloc or "url"
    path = parsed.path or ""
    base = _slug(host + "_" + os.path.basename(path)) or _slug(host)
    if "pdf" in ctype:
        ext = ".pdf"
    elif "html" in ctype or "xhtml" in ctype:
        ext = ".html"
    elif ctype.startswith("image/"):
        ext = "." + (ctype.split("/", 1)[1] or "img").split("+")[0]
    else:
        ext = os.path.splitext(path)[1] or ".bin"

    digest = hashlib.sha1(body).hexdigest()[:8]
    fname = f"{base}_{digest}{ext}"
    dest = os.path.join(out_dir, fname)
    with open(dest, "wb") as f:
        f.write(body)
    return dest


def snapshot_url_rendered(url: str, out_dir: str) -> str:
    """TODO: full-browser render via Playwright (heavier, not yet implemented).

    Once added, this should launch a headless Chromium, navigate, wait for network
    idle, and capture a PDF + full-page screenshot.
    """
    raise NotImplementedError(
        "snapshot_url_rendered requires Playwright. Install with `pip install playwright` "
        "and `playwright install chromium`, then implement headless rendering."
    )
