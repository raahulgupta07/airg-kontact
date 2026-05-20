"""Authentication module for City-KONTACT.

Provides:
- bcrypt password/PIN hashing (passlib)
- E.164 phone normalization (phonenumbers, default region CN)
- Timed signed session tokens (itsdangerous)
- FastAPI `current_user` dependency (cookie OR Authorization: Bearer)
- Role guard factory `require_role(...)`
- Login throttling helpers
- Super-admin bootstrap from environment
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

import phonenumbers

import database as _db

# ─── bcrypt ──────────────────────────────────────────────────────────
_pwd_ctx = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")


def hash_secret(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_secret(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


# ─── identifier normalization ────────────────────────────────────────
def normalize_identifier(s: str) -> Tuple[str, str]:
    """Return (kind, value). kind in {"email","phone","unknown"}."""
    if not s:
        return ("unknown", "")
    s = s.strip()
    if "@" in s:
        return ("email", s.lower())
    # Try phone
    try:
        pn = phonenumbers.parse(s, "CN")
        if phonenumbers.is_valid_number(pn):
            e164 = phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
            return ("phone", e164)
    except Exception:
        pass
    return ("unknown", s)


# ─── tokens ──────────────────────────────────────────────────────────
_INSECURE_SECRETS = {
    "",
    "dev-insecure-session-secret-change-me",
    "replace-this-with-32-random-bytes-base64",
    "changeme",
}


def _session_secret() -> str:
    s = (os.getenv("SESSION_SECRET") or "").strip()
    if s in _INSECURE_SECRETS or len(s) < 32:
        raise RuntimeError(
            "SESSION_SECRET is missing, placeholder, or too short (<32 chars). "
            "Generate one: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
        )
    return s


def _session_days() -> int:
    try:
        return int(os.getenv("SESSION_DAYS", "14"))
    except Exception:
        return 14


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_session_secret(), salt="kontact-session")


def make_token(user_uuid: str) -> str:
    return _serializer().dumps({"uuid": user_uuid, "iat": int(time.time())})


def verify_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=_session_days() * 86400)
        if isinstance(data, dict) and data.get("uuid"):
            return data
    except (BadSignature, SignatureExpired, Exception):
        return None
    return None


# ─── login throttling ────────────────────────────────────────────────
def record_login_attempt(identifier: str, ip: str, success: bool | int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _db.write_lock():
        with _db.db() as c:
            c.execute(
                "INSERT INTO login_attempts(identifier, ip, success, at) VALUES (?,?,?,?)",
                (identifier or "", ip or "", 1 if success else 0, now),
            )
            c.commit()


def is_locked(identifier: str) -> bool:
    """5 fails in last 15min => locked for 30 min from the 5th failure."""
    if not identifier:
        return False
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_15 = (now - timedelta(minutes=15)).isoformat()
    with _db.db() as c:
        rows = c.execute(
            "SELECT at, success FROM login_attempts WHERE identifier = ? AND at >= ? ORDER BY at DESC",
            (identifier, cutoff_15),
        ).fetchall()
    fails = [r for r in rows if not r["success"]]
    if len(fails) < 5:
        return False
    # Time of the 5th most-recent fail
    fifth = fails[4]["at"]
    try:
        fifth_dt = datetime.fromisoformat(fifth)
    except Exception:
        return True
    return (now - fifth_dt) <= timedelta(minutes=30)


# ─── FastAPI dependency ──────────────────────────────────────────────
def _extract_token(request: Request) -> Optional[str]:
    tok = request.cookies.get("kontact_session")
    if tok:
        return tok
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def current_user(request: Request) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    with _db.db() as c:
        row = _db.get_user_by_uuid(c, payload["uuid"])
    if not row:
        raise HTTPException(status_code=401, detail="user not found")
    if not row["is_active"]:
        raise HTTPException(status_code=401, detail="user disabled")
    return {
        "uuid": row["uuid"],
        "name": row["name"],
        "email": row["email"],
        "phone_e164": row["phone_e164"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
    }


def require_role(*roles: str):
    allowed = set(roles)

    def _dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] == "super_admin" or user["role"] in allowed:
            return user
        raise HTTPException(status_code=403, detail="forbidden")

    return _dep


# ─── bootstrap super admin ───────────────────────────────────────────
def bootstrap_super_admin() -> None:
    email = (os.getenv("SUPER_ADMIN_EMAIL") or "").strip().lower() or None
    phone_raw = (os.getenv("SUPER_ADMIN_PHONE") or "").strip() or None
    name = (os.getenv("SUPER_ADMIN_NAME") or "Super Admin").strip()
    password = os.getenv("SUPER_ADMIN_PASSWORD") or ""
    pin = os.getenv("SUPER_ADMIN_PIN") or ""

    if not email and not phone_raw:
        print("[auth] super admin bootstrap skipped: no email/phone in env")
        return
    if not password and not pin:
        print("[auth] super admin bootstrap skipped: no password/pin in env")
        return

    phone_e164 = None
    if phone_raw:
        kind, val = normalize_identifier(phone_raw)
        if kind == "phone":
            phone_e164 = val

    pw_hash = hash_secret(password) if password else None
    pin_hash = hash_secret(pin) if pin else None

    with _db.db() as c:
        existing = None
        if email:
            existing = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not existing and phone_e164:
            existing = c.execute("SELECT * FROM users WHERE phone_e164 = ?", (phone_e164,)).fetchone()
        if existing:
            updates = {
                "name": name,
                "role": "super_admin",
                "is_active": 1,
            }
            if email:
                updates["email"] = email
            if phone_e164:
                updates["phone_e164"] = phone_e164
            if pw_hash:
                updates["password_hash"] = pw_hash
            if pin_hash:
                updates["pin_hash"] = pin_hash
            _db.update_user(c, existing["uuid"], updates)
        else:
            _db.create_user(
                c,
                name=name,
                email=email,
                phone_e164=phone_e164,
                password_hash=pw_hash,
                pin_hash=pin_hash,
                role="super_admin",
                created_by=None,
            )
    print(f"[auth] super admin bootstrapped: {email or phone_e164}")
