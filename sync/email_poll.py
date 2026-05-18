"""IMAP email poller: saves attachments matching SUPPORTED extensions and enqueues them."""
from __future__ import annotations

import email
import hashlib
import imaplib
import os
import re
import threading
import time
from email.header import decode_header
from typing import Optional

import config
import database as db
from pipeline.loader import SUPPORTED

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:
    BackgroundScheduler = None  # type: ignore


_scheduler_state = {
    "scheduler": None,
    "job_id": "kontact_email_poll",
    "config": None,
    "stats": {"polls": 0, "attachments_queued": 0, "errors": 0, "last_run": None},
}
_state_lock = threading.Lock()


def _decode(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            try:
                out.append(txt.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(txt.decode("utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)


def _slugify(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s or "")
    return s.strip("_")[:max_len] or "sender"


def _sender_slug(from_header: str) -> str:
    if not from_header:
        return "unknown"
    m = re.search(r"<([^>]+)>", from_header)
    addr = m.group(1) if m else from_header
    return _slugify(addr.split("@")[0])


def poll_inbox(host: str, user: str, app_password: str, mailbox: str = "INBOX") -> dict:
    """Connect to IMAP, fetch UNSEEN, save matching attachments, enqueue. Returns counts."""
    result = {"host": host, "mailbox": mailbox, "messages": 0, "attachments": 0, "queued": 0, "errors": 0}
    try:
        M = imaplib.IMAP4_SSL(host)
        M.login(user, app_password)
        M.select(mailbox)
        typ, data = M.search(None, "UNSEEN")
        if typ != "OK":
            M.logout()
            return result
        ids = data[0].split()
        result["messages"] = len(ids)
        for msg_id in ids:
            typ, msg_data = M.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            try:
                msg = email.message_from_bytes(raw)
            except Exception:
                result["errors"] += 1
                continue
            from_hdr = _decode(msg.get("From", ""))
            subject = _decode(msg.get("Subject", ""))
            slug = _sender_slug(from_hdr)
            mtime = int(time.time())
            out_dir = os.path.join(config.UPLOADS_DIR, f"email_{slug}_{mtime}")
            os.makedirs(out_dir, exist_ok=True)
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                disp = (part.get("Content-Disposition") or "").lower()
                fname = part.get_filename()
                if not fname:
                    continue
                fname = _decode(fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED:
                    continue
                if "attachment" not in disp and "inline" not in disp:
                    # accept anything with a filename regardless
                    pass
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                result["attachments"] += 1
                fhash = hashlib.sha256(payload).hexdigest()
                if db.file_already_ingested(fhash):
                    continue
                safe_name = _slugify(os.path.splitext(fname)[0], 60) + ext
                dest = os.path.join(out_dir, safe_name)
                try:
                    with open(dest, "wb") as f:
                        f.write(payload)
                except Exception:
                    result["errors"] += 1
                    continue
                batch_id = os.path.basename(out_dir)
                try:
                    db.queue_add(
                        batch_id, safe_name, dest,
                        source_channel="email",
                        source_sender=from_hdr or "unknown",
                        file_hash=fhash,
                    )
                    result["queued"] += 1
                except Exception:
                    result["errors"] += 1
        try:
            M.close()
        except Exception:
            pass
        M.logout()
    except Exception as e:
        result["errors"] += 1
        result["error"] = str(e)
    return result


def _job():
    cfg = _scheduler_state.get("config") or {}
    try:
        r = poll_inbox(cfg["host"], cfg["user"], cfg["app_password"], cfg.get("mailbox", "INBOX"))
        _scheduler_state["stats"]["polls"] += 1
        _scheduler_state["stats"]["attachments_queued"] += r.get("queued", 0)
        _scheduler_state["stats"]["errors"] += r.get("errors", 0)
        _scheduler_state["stats"]["last_run"] = time.time()
        _scheduler_state["stats"]["last_result"] = r
    except Exception as e:
        _scheduler_state["stats"]["errors"] += 1
        _scheduler_state["stats"]["last_error"] = str(e)


def start_poller(host: str, user: str, app_password: str,
                 interval_minutes: int = 5, mailbox: str = "INBOX") -> dict:
    if BackgroundScheduler is None:
        raise RuntimeError("apscheduler not installed. pip install apscheduler")
    with _state_lock:
        if _scheduler_state.get("scheduler") is not None:
            return {"started": False, "reason": "already running"}
        sched = BackgroundScheduler(daemon=True)
        _scheduler_state["config"] = {
            "host": host, "user": user, "app_password": app_password,
            "mailbox": mailbox, "interval_minutes": interval_minutes,
        }
        sched.add_job(_job, "interval", minutes=max(1, int(interval_minutes)),
                     id=_scheduler_state["job_id"], next_run_time=None)
        sched.start()
        _scheduler_state["scheduler"] = sched
        # Kick first poll immediately in background
        threading.Thread(target=_job, daemon=True).start()
    return {"started": True, "interval_minutes": interval_minutes, "host": host, "user": user}


def stop_poller() -> dict:
    with _state_lock:
        sched = _scheduler_state.get("scheduler")
        if not sched:
            return {"stopped": False, "reason": "not running"}
        try:
            sched.shutdown(wait=False)
        except Exception:
            pass
        _scheduler_state["scheduler"] = None
        cfg = _scheduler_state.get("config")
        _scheduler_state["config"] = None
    return {"stopped": True, "was": {"host": cfg.get("host") if cfg else None}}


def poller_status() -> dict:
    cfg = _scheduler_state.get("config") or {}
    return {
        "running": _scheduler_state.get("scheduler") is not None,
        "host": cfg.get("host"),
        "user": cfg.get("user"),
        "mailbox": cfg.get("mailbox"),
        "interval_minutes": cfg.get("interval_minutes"),
        "stats": dict(_scheduler_state.get("stats", {})),
    }
