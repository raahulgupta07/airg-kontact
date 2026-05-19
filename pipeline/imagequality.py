import os

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import imagehash
except ImportError:
    imagehash = None

from PIL import Image

# Laplacian variance < threshold = blurry.
# 100 was too strict for client-compressed JPEGs (q=0.85, 2000px max)
# which introduce mild high-freq attenuation. 40 keeps obvious blur
# (var ~5-15) while letting sharp compressed photos (var ~80-400) pass.
# Env override: BLUR_THRESHOLD=<float>
BLUR_THRESHOLD = float(os.getenv("BLUR_THRESHOLD", "20"))


from typing import Optional


def compute_phash(path: str) -> Optional[str]:
    if imagehash is None:
        return None
    try:
        img = Image.open(path)
        return str(imagehash.phash(img, hash_size=8))  # 16 hex chars
    except Exception:
        return None


def compute_blur(path: str) -> Optional[float]:
    if cv2 is None:
        return None
    try:
        gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return None
        # Resize for consistency
        h, w = gray.shape
        if max(h, w) > 1024:
            scale = 1024 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return None


def is_blurry(score: Optional[float]) -> bool:
    return score is not None and score < BLUR_THRESHOLD


def find_near_dup(c, phash: str, hamming_threshold: int = 5) -> Optional[str]:
    """Find earlier doc with similar phash. Returns uuid or None."""
    if not phash or imagehash is None:
        return None
    try:
        rows = c.execute(
            "SELECT uuid, image_phash FROM documents WHERE image_phash IS NOT NULL"
        ).fetchall()
    except Exception:
        return None
    try:
        target = imagehash.hex_to_hash(phash)
    except Exception:
        return None
    for row in rows:
        other_hex = row["image_phash"] if hasattr(row, "keys") else row[1]
        row_uuid = row["uuid"] if hasattr(row, "keys") else row[0]
        if other_hex == phash:
            return row_uuid
        try:
            other = imagehash.hex_to_hash(other_hex)
            if (target - other) <= hamming_threshold:
                return row_uuid
        except Exception:
            continue
    return None
