"""One-time migration: copy existing local uploads to the configured S3 backend.

Usage:
    # Inside container (after setting S3_* env vars + STORAGE_BACKEND=s3)
    docker compose exec kontact python3 migrate_to_s3.py

    # Or locally
    STORAGE_BACKEND=s3 S3_BUCKET=... AWS_ACCESS_KEY_ID=... \
      AWS_SECRET_ACCESS_KEY=... python3 migrate_to_s3.py

Safe to re-run — uses head_object to skip files already present.
"""
from __future__ import annotations

import os
import sys

import config
from storage import storage, upload_key


def main():
    if storage.backend_name() != "s3":
        print("STORAGE_BACKEND is not 's3'. Set env then re-run.")
        sys.exit(1)

    root = config.UPLOADS_DIR
    if not os.path.isdir(root):
        print(f"No uploads dir at {root}")
        return

    total = 0
    pushed = 0
    skipped = 0
    failed = 0

    for folder in sorted(os.listdir(root)):
        folder_path = os.path.join(root, folder)
        if not os.path.isdir(folder_path):
            continue
        for fname in sorted(os.listdir(folder_path)):
            src = os.path.join(folder_path, fname)
            if not os.path.isfile(src):
                continue
            total += 1
            key = upload_key(folder, fname)
            try:
                if storage.exists(key):
                    skipped += 1
                    continue
                ctype = None
                ext = os.path.splitext(fname)[1].lower()
                if ext in (".jpg", ".jpeg"):
                    ctype = "image/jpeg"
                elif ext == ".png":
                    ctype = "image/png"
                elif ext == ".pdf":
                    ctype = "application/pdf"
                storage.save_file(key, src, ctype)
                pushed += 1
                if pushed % 25 == 0:
                    print(f"  ... {pushed} uploaded")
            except Exception as e:
                failed += 1
                print(f"FAIL {key}: {e}")

    print(f"\nDone. total={total} pushed={pushed} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
