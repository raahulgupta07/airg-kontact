"""WeChat desktop file watcher.

Watches a WeChat desktop file storage folder for new images/PDFs, computes
content hash, dedupes against the kontact DB, infers vendor from the parent
chat folder (via wechat_chat_map), and enqueues files for the extractor.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Optional

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # watchdog is optional at import time
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore

from pipeline.loader import SUPPORTED
import database as db


_state = {
    "observer": None,
    "folder": None,
    "handler": None,
    "stats": {"seen": 0, "queued": 0, "skipped_dup": 0, "errors": 0},
    "started_at": None,
}
_lock = threading.Lock()


def _hash_file(path: str, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:
        return ""


def _chat_hash_for(path: str, root: str) -> str:
    """Use the immediate parent folder name (relative to watch root) as a stable chat id.

    WeChat desktop typically stores per-chat folders named with opaque hashes,
    so the folder name itself is a stable handle.
    """
    try:
        parent = os.path.basename(os.path.dirname(path))
    except Exception:
        parent = ""
    if not parent:
        parent = os.path.basename(root.rstrip(os.sep))
    return hashlib.sha1(parent.encode("utf-8", errors="replace")).hexdigest()[:16] if parent else "wechat"


def _process_path(path: str, root: str) -> None:
    if not os.path.isfile(path):
        return
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        return
    _state["stats"]["seen"] += 1

    # Give WeChat a moment to finish writing.
    time.sleep(2.0)

    fhash = _hash_file(path)
    if not fhash:
        _state["stats"]["errors"] += 1
        return

    if db.file_already_ingested(fhash):
        _state["stats"]["skipped_dup"] += 1
        return

    chat_hash = _chat_hash_for(path, root)
    mapping = db.wechat_map_get(chat_hash) or {}
    vendor = mapping.get("vendor_company") if mapping else None

    try:
        mtime = int(os.path.getmtime(path))
    except Exception:
        mtime = int(time.time())

    short = (vendor or chat_hash)[:24]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in short) or "wechat"
    batch_id = f"wechat_{safe}_{mtime}"
    sender = vendor or chat_hash

    fname = os.path.basename(path)
    try:
        db.queue_add(
            batch_id, fname, path,
            source_channel="wechat_desktop",
            source_sender=sender,
            file_hash=fhash,
        )
        _state["stats"]["queued"] += 1
    except Exception:
        _state["stats"]["errors"] += 1


class _WeChatHandler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, root: str):
        super().__init__()
        self.root = root

    def on_created(self, event):  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        try:
            _process_path(event.src_path, self.root)
        except Exception:
            _state["stats"]["errors"] += 1

    def on_moved(self, event):  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        dest = getattr(event, "dest_path", None)
        if dest:
            try:
                _process_path(dest, self.root)
            except Exception:
                _state["stats"]["errors"] += 1


def start_watcher(folder_path: str) -> dict:
    if Observer is None:
        raise RuntimeError("watchdog not installed. pip install watchdog")
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Not a directory: {folder_path}")
    with _lock:
        if _state["observer"] is not None:
            return {"started": False, "reason": "already watching", "folder": _state["folder"]}
        handler = _WeChatHandler(folder_path)
        obs = Observer()
        obs.schedule(handler, folder_path, recursive=True)
        obs.daemon = True
        obs.start()
        _state["observer"] = obs
        _state["handler"] = handler
        _state["folder"] = folder_path
        _state["started_at"] = time.time()
    return {"started": True, "folder": folder_path}


def stop_watcher() -> dict:
    with _lock:
        obs = _state.get("observer")
        if not obs:
            return {"stopped": False, "reason": "not running"}
        try:
            obs.stop()
            obs.join(timeout=5)
        except Exception:
            pass
        _state["observer"] = None
        folder = _state.get("folder")
        _state["folder"] = None
        _state["handler"] = None
        _state["started_at"] = None
    return {"stopped": True, "folder": folder}


def watcher_status() -> dict:
    return {
        "watching": _state.get("observer") is not None,
        "folder": _state.get("folder"),
        "started_at": _state.get("started_at"),
        "stats": dict(_state.get("stats", {})),
    }


def scan_folder_once(folder_path: str, vendor_company: Optional[str] = None) -> dict:
    """One-shot recursive scan of a WeChat folder. Returns counts."""
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Not a directory: {folder_path}")
    queued = 0
    skipped = 0
    seen = 0
    for dirpath, _dirs, files in os.walk(folder_path):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED:
                continue
            full = os.path.join(dirpath, fname)
            seen += 1
            fhash = _hash_file(full)
            if not fhash or db.file_already_ingested(fhash):
                skipped += 1
                continue
            chat_hash = _chat_hash_for(full, folder_path)
            mapping = db.wechat_map_get(chat_hash) or {}
            vendor = vendor_company or mapping.get("vendor_company")
            try:
                mtime = int(os.path.getmtime(full))
            except Exception:
                mtime = int(time.time())
            short = (vendor or chat_hash)[:24]
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in short) or "wechat"
            batch_id = f"wechat_{safe}_{mtime}"
            try:
                db.queue_add(
                    batch_id, fname, full,
                    source_channel="wechat_desktop",
                    source_sender=vendor or chat_hash,
                    file_hash=fhash,
                )
                queued += 1
            except Exception:
                pass
    return {"folder": folder_path, "seen": seen, "queued": queued, "skipped_duplicates": skipped}
