import base64, logging, os, re
from urllib.parse import urlparse, parse_qs, unquote
from PIL import Image, UnidentifiedImageError
from PIL.ExifTags import TAGS, GPSTAGS
from io import BytesIO

log = logging.getLogger("kontact.pipeline.loader")

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    from pyzbar import pyzbar
except ImportError:
    pyzbar = None

try:
    import phonenumbers
except ImportError:
    phonenumbers = None

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

SUPPORTED = {".jpg", ".jpeg", ".png", ".jfif", ".webp", ".bmp", ".heic", ".heif", ".tiff", ".tif", ".avif", ".gif", ".pdf"}
MAX_PX = 4096


def _gps_to_decimal(gps_info):
    """Convert GPS EXIF to decimal degrees."""
    def _convert(value):
        d, m, s = value
        return float(d) + float(m)/60 + float(s)/3600

    lat = _convert(gps_info.get(2, (0, 0, 0)))
    lng = _convert(gps_info.get(4, (0, 0, 0)))
    if gps_info.get(1) == 'S':
        lat = -lat
    if gps_info.get(3) == 'W':
        lng = -lng
    return lat, lng


def _to_float(v):
    """Safely convert EXIF rational / IFDRational / tuple → float."""
    if v is None:
        return None
    try:
        if isinstance(v, tuple) and len(v) == 2:
            return float(v[0]) / float(v[1]) if v[1] else None
        return float(v)
    except Exception:
        return None


def _to_int(v):
    if v is None:
        return None
    try:
        if isinstance(v, (list, tuple)) and v:
            return int(v[0])
        return int(v)
    except Exception:
        return None


def _exposure_str(v):
    """Convert ExposureTime (IFDRational or float) → '1/120' string."""
    if v is None:
        return None
    try:
        if isinstance(v, tuple) and len(v) == 2:
            num, den = v
            if num and den:
                if num == 1:
                    return f"1/{int(den)}"
                # Reduce: try fractions
                from fractions import Fraction
                f = Fraction(int(num), int(den)).limit_denominator(10000)
                if f.numerator == 1:
                    return f"1/{f.denominator}"
                return f"{f.numerator}/{f.denominator}"
        fv = float(v)
        if fv <= 0:
            return None
        if fv >= 1:
            return f"{fv:.1f}"
        # Sub-second exposure → reciprocal form
        return f"1/{int(round(1.0 / fv))}"
    except Exception:
        return None


def extract_exif(path: str) -> dict:
    """Extract EXIF metadata from an image file."""
    meta = {
        "gps_lat": None,
        "gps_lng": None,
        "gps_altitude": None,
        "gps_heading": None,
        "gps_speed": None,
        "date_taken": None,
        "camera_make": None,
        "camera_model": None,
        "lens_model": None,
        "focal_length": None,
        "f_number": None,
        "iso": None,
        "exposure_time": None,
        "software": None,
        "sub_sec_time": None,
        "width": None,
        "height": None,
        "orientation": None,
        "file_size_kb": round(os.path.getsize(path) / 1024, 1) if os.path.isfile(path) else None,
    }
    try:
        img = Image.open(path)
        meta["width"], meta["height"] = img.size

        exif_data = img.getexif()
        if not exif_data:
            return meta

        # Build tag name lookup (top-level IFD0)
        tag_map = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            tag_map[tag_name] = value

        # Pull EXIF sub-IFD (where most camera fields actually live)
        exif_ifd = {}
        try:
            sub = exif_data.get_ifd(0x8769)  # ExifOffset
            if sub:
                for tid, val in sub.items():
                    name = TAGS.get(tid, tid)
                    exif_ifd[name] = val
        except Exception:
            pass

        def _g(name):
            if name in exif_ifd:
                return exif_ifd[name]
            return tag_map.get(name)

        meta["date_taken"] = _g("DateTimeOriginal") or _g("DateTime")
        meta["camera_make"] = tag_map.get("Make")
        meta["camera_model"] = tag_map.get("Model")
        meta["orientation"] = tag_map.get("Orientation")
        meta["software"] = tag_map.get("Software") or _g("Software")
        meta["lens_model"] = _g("LensModel")
        meta["sub_sec_time"] = _g("SubSecTimeOriginal") or _g("SubSecTime")

        meta["focal_length"] = _to_float(_g("FocalLength"))
        meta["f_number"] = _to_float(_g("FNumber"))
        iso_val = _g("ISOSpeedRatings") or _g("PhotographicSensitivity")
        meta["iso"] = _to_int(iso_val)
        meta["exposure_time"] = _exposure_str(_g("ExposureTime"))

        if tag_map.get("ExifImageWidth") or exif_ifd.get("ExifImageWidth"):
            meta["width"] = tag_map.get("ExifImageWidth") or exif_ifd.get("ExifImageWidth")
        if tag_map.get("ExifImageHeight") or exif_ifd.get("ExifImageHeight"):
            meta["height"] = tag_map.get("ExifImageHeight") or exif_ifd.get("ExifImageHeight")

        # GPS info
        gps_ifd = exif_data.get_ifd(0x8825)
        if gps_ifd:
            try:
                lat, lng = _gps_to_decimal(gps_ifd)
                if lat != 0.0 or lng != 0.0:
                    meta["gps_lat"] = round(lat, 6)
                    meta["gps_lng"] = round(lng, 6)
            except Exception:
                pass

            # Altitude (tag 6 / ref tag 5)
            try:
                alt = _to_float(gps_ifd.get(6))
                if alt is not None:
                    alt_ref = gps_ifd.get(5)
                    # alt_ref: 0 above sea, 1 below sea
                    if alt_ref in (1, b"\x01"):
                        alt = -alt
                    meta["gps_altitude"] = round(alt, 2)
            except Exception:
                pass

            # Image direction / heading (tag 17)
            try:
                heading = _to_float(gps_ifd.get(17))
                if heading is not None:
                    meta["gps_heading"] = round(heading, 2)
            except Exception:
                pass

            # Speed (tag 13 / ref tag 12: K=km/h, M=mph, N=knots)
            try:
                speed = _to_float(gps_ifd.get(13))
                if speed is not None:
                    speed_ref = gps_ifd.get(12)
                    if isinstance(speed_ref, bytes):
                        try:
                            speed_ref = speed_ref.decode("ascii", "ignore")
                        except Exception:
                            speed_ref = ""
                    speed_ref = (speed_ref or "K").strip().upper()
                    if speed_ref == "K":      # km/h → m/s
                        speed_ms = speed * 1000.0 / 3600.0
                    elif speed_ref == "M":    # mph → m/s
                        speed_ms = speed * 1609.344 / 3600.0
                    elif speed_ref == "N":    # knots → m/s
                        speed_ms = speed * 0.514444
                    else:
                        speed_ms = speed
                    meta["gps_speed"] = round(speed_ms, 3)
            except (TypeError, ValueError, AttributeError):
                pass
    except (UnidentifiedImageError, OSError) as e:
        log.warning("extract_exif failed for %s: %s", path, e)
    except Image.DecompressionBombError as e:
        log.error("decompression bomb suspected: %s (%s)", path, e)
    return meta


# ---------------------------------------------------------------------------
# QR code extraction + messenger parsing
# ---------------------------------------------------------------------------

_QR_PATTERNS = [
    ("whatsapp_group", re.compile(r"^https?://(chat\.)?whatsapp\.com/(invite/)?[A-Za-z0-9]+", re.I)),
    ("whatsapp",       re.compile(r"^(https?://)?(wa\.me|api\.whatsapp\.com|whatsapp://)", re.I)),
    ("viber",          re.compile(r"^viber://", re.I)),
    ("telegram",       re.compile(r"^(https?://)?(t\.me|telegram\.me|tg://)", re.I)),
    ("line",           re.compile(r"^(https?://)?(line\.me|lin\.ee|line://)", re.I)),
    ("signal",         re.compile(r"^(https?://)?signal\.(me|group)|sgnl://", re.I)),
    ("kakao",          re.compile(r"^(https?://)?(open\.kakao\.com|qr\.kakao\.com|kakaotalk://)", re.I)),
    ("wechat",         re.compile(r"^(https?://)?(weixin\.qq\.com|u\.wechat\.com|wxp://|weixin://)", re.I)),
    ("skype",          re.compile(r"^(skype:|https?://join\.skype\.com)", re.I)),
    ("zalo",           re.compile(r"^(https?://)?(zalo\.me|zalo://)", re.I)),
    ("messenger",      re.compile(r"^(https?://)?(m\.me|messenger\.com|fb-messenger://)", re.I)),
    ("instagram",      re.compile(r"^(https?://)?(www\.)?instagram\.com/", re.I)),
    ("snapchat",       re.compile(r"^(https?://)?(www\.)?snapchat\.com/add/", re.I)),
    ("discord",        re.compile(r"^(https?://)?(discord\.gg|discord\.com/invite)", re.I)),
    ("vcard",          re.compile(r"^BEGIN:VCARD", re.I)),
    ("mecard",         re.compile(r"^MECARD:", re.I)),
    ("tel",            re.compile(r"^tel:", re.I)),
    ("email",          re.compile(r"^(mailto:|MATMSG:)", re.I)),
    ("sms",            re.compile(r"^sms(to)?:", re.I)),
    ("wifi",           re.compile(r"^WIFI:", re.I)),
    ("geo",            re.compile(r"^geo:", re.I)),
    ("url",            re.compile(r"^https?://", re.I)),
]


def _classify_qr(raw: str) -> str:
    if not raw:
        return "text"
    s = raw.strip()
    for name, pat in _QR_PATTERNS:
        if pat.search(s):
            return name
    return "text"


def _normalize_phone(s, default_region="CN"):
    if not s or phonenumbers is None:
        return s if s else None
    try:
        # strip non-phone chars but keep + and digits
        cleaned = re.sub(r"[^\d+]", "", str(s))
        if not cleaned:
            return None
        num = phonenumbers.parse(cleaned, None if cleaned.startswith("+") else default_region)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return None


def parse_vcard(raw: str) -> dict:
    out = {"person": None, "company": None, "phone": None, "email": None,
           "website": None, "address": None, "title": None}
    if not raw:
        return out
    # Unfold continuation lines (RFC 6350)
    text = re.sub(r"\r?\n[ \t]", "", raw)
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key_up = key.upper().split(";")[0]
        val = val.strip()
        if key_up == "FN" and not out["person"]:
            out["person"] = val
        elif key_up == "N" and not out["person"]:
            parts = [p for p in val.split(";") if p]
            out["person"] = " ".join(reversed(parts[:2])) if parts else val
        elif key_up == "ORG":
            out["company"] = val.split(";")[0]
        elif key_up == "TEL":
            out["phone"] = _normalize_phone(val) or val
        elif key_up == "EMAIL":
            out["email"] = val
        elif key_up == "URL":
            out["website"] = val
        elif key_up == "ADR":
            out["address"] = ", ".join([p for p in val.split(";") if p])
        elif key_up == "TITLE":
            out["title"] = val
    return out


def parse_mecard(raw: str) -> dict:
    out = {"person": None, "company": None, "phone": None, "email": None,
           "website": None, "address": None, "title": None}
    if not raw:
        return out
    body = raw.strip()
    if body.upper().startswith("MECARD:"):
        body = body[7:]
    if body.endswith(";;"):
        body = body[:-2]
    for field in body.split(";"):
        if ":" not in field:
            continue
        k, _, v = field.partition(":")
        k = k.upper()
        if k == "N":
            parts = [p for p in v.split(",") if p]
            out["person"] = " ".join(reversed(parts)) if len(parts) > 1 else v
        elif k == "ORG":
            out["company"] = v
        elif k == "TEL":
            out["phone"] = _normalize_phone(v) or v
        elif k == "EMAIL":
            out["email"] = v
        elif k == "URL":
            out["website"] = v
        elif k == "ADR":
            out["address"] = v
        elif k == "TITLE":
            out["title"] = v
    return out


def parse_messenger_qr(qr_type: str, raw: str) -> dict:
    out = {"platform": qr_type, "raw": raw, "handle": None, "phone": None, "deeplink": raw}
    if not raw:
        return out
    s = raw.strip()
    try:
        parsed = urlparse(s if "://" in s else "https://" + s)
    except Exception:
        parsed = None
    host = (parsed.netloc.lower() if parsed else "")
    path = (parsed.path or "") if parsed else ""
    query = parse_qs(parsed.query) if parsed else {}
    seg = [p for p in path.split("/") if p]

    if qr_type == "whatsapp":
        # wa.me/<phone>, wa.me/qr/<code>, wa.me/message/<code>,
        # api.whatsapp.com/send?phone=..., whatsapp://send?phone=...
        phone = None
        invite_code = None
        if "wa.me" in host or "api.whatsapp.com" in host:
            if "phone" in query:
                phone = query["phone"][0]
            elif len(seg) >= 2 and seg[0].lower() in ("qr", "message"):
                invite_code = seg[1]
            elif seg:
                # First segment should be digits to be a phone
                first = seg[0].lstrip("+")
                if first.isdigit():
                    phone = seg[0]
                else:
                    invite_code = seg[0]
        elif s.lower().startswith("whatsapp://"):
            qs = parse_qs(parsed.query) if parsed else {}
            phone = qs.get("phone", [None])[0]
        if phone:
            out["phone"] = _normalize_phone(phone) or phone
            out["handle"] = out["phone"]
        elif invite_code:
            out["invite_code"] = invite_code
            out["handle"] = invite_code
            out["phone"] = None
    elif qr_type == "whatsapp_group":
        out["handle"] = seg[-1] if seg else None
    elif qr_type == "viber":
        # viber://chat?number=+...  viber://add?number=...
        qs = parse_qs(parsed.query) if parsed else {}
        phone = qs.get("number", [None])[0] or qs.get("phone", [None])[0]
        out["phone"] = _normalize_phone(phone) or phone
        out["handle"] = out["phone"]
    elif qr_type == "telegram":
        # t.me/<handle> or t.me/+phone or tg://resolve?domain=<handle>
        if "tg://" in s.lower():
            qs = parse_qs(parsed.query) if parsed else {}
            out["handle"] = qs.get("domain", [None])[0] or qs.get("phone", [None])[0]
        elif seg:
            first = seg[0]
            if first.startswith("+"):
                out["phone"] = _normalize_phone(first) or first
                out["handle"] = out["phone"]
            else:
                out["handle"] = first
    elif qr_type == "line":
        # line.me/ti/p/<id>  lin.ee/<code>  line.me/R/ti/p/~<id>
        if seg:
            out["handle"] = seg[-1].lstrip("~")
    elif qr_type == "signal":
        # signal.me/#p/+phone
        frag = parsed.fragment if parsed else ""
        m = re.search(r"\+?\d+", frag or path)
        if m:
            out["phone"] = _normalize_phone(m.group(0)) or m.group(0)
            out["handle"] = out["phone"]
    elif qr_type == "kakao":
        out["handle"] = None  # opaque
    elif qr_type == "wechat":
        out["handle"] = None  # opaque
    elif qr_type == "skype":
        # skype:<handle>?chat
        m = re.match(r"skype:([^?]+)", s, re.I)
        if m:
            out["handle"] = unquote(m.group(1))
    elif qr_type == "zalo":
        # zalo.me/<phone>
        if seg:
            cand = seg[-1]
            out["phone"] = _normalize_phone(cand) or cand
            out["handle"] = out["phone"]
    elif qr_type == "messenger":
        # m.me/<handle>
        if seg:
            out["handle"] = seg[-1]
    elif qr_type == "instagram":
        if seg:
            out["handle"] = seg[0]
    elif qr_type == "snapchat":
        # snapchat.com/add/<handle>
        if seg and seg[0].lower() == "add" and len(seg) > 1:
            out["handle"] = seg[1]
        elif seg:
            out["handle"] = seg[-1]
    elif qr_type == "discord":
        if seg:
            out["handle"] = seg[-1]
    return out


def extract_qr_codes(path: str) -> list[dict]:
    """Decode QR codes from an image. Returns list of {raw, type, parsed}."""
    if cv2 is None:
        return []
    try:
        img = cv2.imread(path)
        if img is None:
            return []
    except Exception:
        return []

    decoded_raws: list[str] = []

    def _decode_with_pyzbar(image):
        out = []
        if pyzbar is None:
            return out
        try:
            for d in pyzbar.decode(image):
                try:
                    raw = d.data.decode("utf-8", errors="replace")
                except Exception:
                    raw = str(d.data)
                if raw:
                    out.append(raw)
        except Exception:
            pass
        return out

    def _decode_with_cv2(image):
        try:
            detector = cv2.QRCodeDetector()
            retval, decoded_info, points, _ = detector.detectAndDecodeMulti(image)
            if retval and decoded_info:
                return [s for s in decoded_info if s]
            data, pts, _ = detector.detectAndDecode(image)
            if data:
                return [data]
        except Exception:
            pass
        return []

    decoded_raws = _decode_with_pyzbar(img)
    if not decoded_raws:
        decoded_raws = _decode_with_cv2(img)

    # Fallback: rotate per EXIF orientation if still empty
    if not decoded_raws:
        try:
            orientation = extract_exif(path).get("orientation")
            rotations = {3: cv2.ROTATE_180, 6: cv2.ROTATE_90_CLOCKWISE, 8: cv2.ROTATE_90_COUNTERCLOCKWISE}
            if orientation in rotations:
                rot = cv2.rotate(img, rotations[orientation])
                decoded_raws = _decode_with_pyzbar(rot) or _decode_with_cv2(rot)
        except Exception:
            pass

    # Last resort: try every 90 degree rotation
    if not decoded_raws:
        for rot_code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE):
            try:
                rot = cv2.rotate(img, rot_code)
            except Exception:
                continue
            decoded_raws = _decode_with_pyzbar(rot) or _decode_with_cv2(rot)
            if decoded_raws:
                break

    results = []
    seen = set()
    for raw in decoded_raws:
        if raw in seen:
            continue
        seen.add(raw)
        qr_type = _classify_qr(raw)
        if qr_type == "vcard":
            parsed = parse_vcard(raw)
        elif qr_type == "mecard":
            parsed = parse_mecard(raw)
        elif qr_type in {"whatsapp", "whatsapp_group", "viber", "telegram", "line",
                         "signal", "kakao", "wechat", "skype", "zalo", "messenger",
                         "instagram", "snapchat", "discord"}:
            parsed = parse_messenger_qr(qr_type, raw)
        else:
            parsed = {}
        results.append({"raw": raw, "type": qr_type, "parsed": parsed})
    return results


def load_pdf(path: str) -> list[dict]:
    """Convert each page of a PDF to a JPEG image and return list of dicts."""
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    results = []
    base_name = os.path.splitext(os.path.basename(path))[0]
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        w, h = img.size
        if max(w, h) > MAX_PX:
            ratio = MAX_PX / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)
        b64 = base64.b64encode(buf.getvalue()).decode()
        page_name = f"{base_name}_page{i}.jpg"
        results.append({"file": page_name, "path": path, "image_b64": b64})
    doc.close()
    return results


def load_image(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return load_pdf(path)
    metadata = extract_exif(path)
    try:
        metadata["qr_codes"] = extract_qr_codes(path)
    except (OSError, ValueError, RuntimeError) as e:
        log.warning("qr extraction failed for %s: %s", path, e)
        metadata["qr_codes"] = []
    try:
        from pipeline.imagequality import compute_blur, is_blurry as _ib
        bs = compute_blur(path)
        if bs is not None:
            metadata["blur_score"] = bs
            metadata["is_blurry"] = bool(_ib(bs))
    except (OSError, ImportError, ValueError) as e:
        log.warning("blur check failed for %s: %s", path, e)
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_PX:
        ratio = MAX_PX / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"file": os.path.basename(path), "path": path, "image_b64": b64, "metadata": metadata}


def load_folder(folder: str) -> list[dict]:
    images = []
    for f in sorted(os.listdir(folder)):
        if os.path.splitext(f)[1].lower() in SUPPORTED:
            images.append(load_image(os.path.join(folder, f)))
    return images
