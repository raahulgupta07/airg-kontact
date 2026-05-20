import httpx, asyncio, json
import config
from pipeline.agents import CLASSIFIER_PROMPT, AGENT_PROMPTS

# Messenger platforms that get promoted to flat contact fields
_MESSENGER_PLATFORMS = {
    "whatsapp", "whatsapp_group", "viber", "telegram", "line", "signal",
    "kakao", "wechat", "skype", "zalo", "messenger", "instagram",
    "snapchat", "discord",
}


def merge_qr_into_data(data: dict, qr_codes: list) -> dict:
    """Merge decoded QR codes into the extractor output dict.

    - Builds data['messengers'] (list of platform records).
    - Promotes well-known platforms to flat fields under data['contact'].
    - Serialises raw QR payloads to data['qr_payloads'] (JSON string).
    - Overlays vCard fields onto data['contact'] (vCard is authoritative).
    """
    if not qr_codes:
        return data

    data.setdefault("contact", {})
    contact = data["contact"]
    messengers = []
    payloads = []

    for qr in qr_codes:
        qr_type = qr.get("type", "text")
        raw = qr.get("raw", "")
        parsed = qr.get("parsed") or {}
        payloads.append({"type": qr_type, "raw": raw, "parsed": parsed})

        if qr_type in _MESSENGER_PLATFORMS:
            messengers.append({
                "platform": qr_type,
                "handle": parsed.get("handle"),
                "phone": parsed.get("phone"),
                "deeplink": parsed.get("deeplink") or raw,
                "raw": raw,
            })

        # Promote known platforms to flat contact fields (don't overwrite truthy values)
        if qr_type == "whatsapp" and not contact.get("whatsapp"):
            # Prefer real phone; otherwise keep the deeplink so user can tap to chat
            contact["whatsapp"] = parsed.get("phone") or raw
        elif qr_type == "viber" and not contact.get("viber"):
            contact["viber"] = parsed.get("phone") or raw
        elif qr_type == "telegram" and not contact.get("telegram"):
            contact["telegram"] = parsed.get("handle") or parsed.get("phone") or raw
        elif qr_type == "line" and not contact.get("line_id"):
            contact["line_id"] = parsed.get("handle") or raw
        elif qr_type == "signal" and not contact.get("signal_phone"):
            contact["signal_phone"] = parsed.get("phone") or raw
        elif qr_type == "wechat" and not contact.get("wechat_qr_url"):
            contact["wechat_qr_url"] = raw

        # Communication-only QRs fill contact gaps
        elif qr_type == "tel" and not contact.get("phone"):
            contact["phone"] = parsed.get("phone") or raw
        elif qr_type == "email" and not contact.get("email"):
            if parsed.get("email"):
                contact["email"] = parsed["email"]
        elif qr_type == "sms":
            if not contact.get("phone") and parsed.get("phone"):
                contact["phone"] = parsed["phone"]

        # GeoURL → page-level GPS (overrides only if EXIF missing)
        elif qr_type == "geo":
            data.setdefault("metadata", {})
            if data["metadata"].get("gps_lat") is None and parsed.get("gps_lat") is not None:
                data["metadata"]["gps_lat"] = parsed["gps_lat"]
                data["metadata"]["gps_lng"] = parsed["gps_lng"]
                data["metadata"]["gps_source"] = "qr_geo"

        # VEVENT → meeting record (created downstream by main.py)
        elif qr_type == "vevent":
            data.setdefault("meetings", []).append({
                "title": parsed.get("title"),
                "location": parsed.get("location"),
                "when_at": parsed.get("start"),
                "end_at": parsed.get("end"),
                "description": parsed.get("description"),
                "organizer": parsed.get("organizer"),
            })

        # WiFi → metadata only (not contact)
        elif qr_type == "wifi":
            data.setdefault("metadata", {})["wifi"] = {
                "ssid": parsed.get("ssid"),
                "auth": parsed.get("auth"),
                "hidden": parsed.get("hidden"),
                # NOTE: do not expose plaintext password in flat columns
                "password_present": bool(parsed.get("password")),
            }

        # Payments (EPC/UPI/PIX/crypto) → metadata, not contact
        elif qr_type in ("epc", "upi", "pix", "bitcoin", "ethereum"):
            data.setdefault("metadata", {}).setdefault("payments", []).append({
                "type": qr_type,
                **parsed,
            })

        # Barcode (1D EAN/UPC/Code128 etc.) → product hint
        elif qr_type == "barcode":
            data.setdefault("metadata", {}).setdefault("barcodes", []).append({
                "code": parsed.get("code") or raw,
                "symbology": parsed.get("symbology"),
            })

    # vCard / MeCard overlay — authoritative for contact
    for qr in qr_codes:
        if qr.get("type") in ("vcard", "mecard"):
            card = qr.get("parsed") or {}
            for k, v in card.items():
                if v:
                    contact[k] = v
            if card.get("company") and not data.get("company"):
                data["company"] = card["company"]

    if messengers:
        data["messengers"] = messengers
    data["qr_payloads"] = json.dumps(payloads, ensure_ascii=False)
    return data

HEADERS = {
    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
}


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


async def _call_vision(client, img_b64: str, system: str, user_text: str, sem) -> dict:
    async with sem:
        payload = {
            "model": config.VISION_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text", "text": user_text}
                ]}
            ],
            "max_tokens": 4000,
            "temperature": 0,
        }
        for attempt in range(3):
            try:
                r = await client.post(config.OPENROUTER_BASE, json=payload, headers=HEADERS, timeout=120)
                r.raise_for_status()
                body = r.json()
                try:
                    import database as _db
                    usage = body.get("usage") or {}
                    _db.log_llm_usage(
                        user_uuid=None,  # batch context; owner attribution downstream
                        op="extract",
                        model=config.VISION_MODEL,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                    )
                except Exception:
                    pass
                return _parse_json(body["choices"][0]["message"]["content"])
            except Exception as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)


async def extract_one(client: httpx.AsyncClient, img: dict, sem: asyncio.Semaphore) -> dict:
    b64 = img["image_b64"]

    # Skip LLM extraction on blurry images to prevent hallucinated fields
    pre_meta = img.get("metadata") if isinstance(img, dict) else None
    if isinstance(pre_meta, dict) and pre_meta.get("is_blurry"):
        return {
            "source_file": img.get("file", ""),
            "source_path": img.get("path", ""),
            "image_type": "blurry",
            "classifier_confidence": 0,
            "title": "(blurry — extraction skipped)",
            "company": None,
            "products": [],
            "contact": {},
            "key_info": [],
            "raw_text": "",
            "metadata": pre_meta,
            "skipped_reason": "blur",
        }

    # Step 1: Classify
    classification = await _call_vision(client, b64, CLASSIFIER_PROMPT, "Classify this image.", sem)
    img_type = classification.get("image_type", "other")
    if img_type not in AGENT_PROMPTS:
        img_type = "other"

    # Step 2: Extract with specialized agent
    agent_prompt = AGENT_PROMPTS[img_type]
    try:
        data = await _call_vision(client, b64, agent_prompt, "Extract all data from this image.", sem)
    except Exception as e:
        return {"source_file": img["file"], "source_path": img.get("path", ""), "error": str(e)}

    data["image_type"] = img_type
    data["classifier_confidence"] = classification.get("confidence", 0)
    data["source_file"] = img["file"]
    data["source_path"] = img.get("path", "")

    # Normalize: ensure products/contact/key_info exist
    data.setdefault("products", [])
    data.setdefault("contact", {})
    data.setdefault("key_info", [])
    data.setdefault("raw_text", "")
    data.setdefault("company", None)
    data.setdefault("title", "")

    # Merge QR codes decoded by the loader (single-image path only; PDF pages skipped)
    qr_codes = []
    meta = img.get("metadata") if isinstance(img, dict) else None
    if isinstance(meta, dict):
        qr_codes = meta.get("qr_codes") or []
    if qr_codes:
        data = merge_qr_into_data(data, qr_codes)

    # Propagate loader-side EXIF/quality metadata into the result so downstream
    # write-path (insert_extraction → flat columns) can read gps_lat, camera_*, etc.
    if isinstance(meta, dict):
        existing_meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        merged = dict(existing_meta)
        for k, v in meta.items():
            if v is not None:
                merged[k] = v
        data["metadata"] = merged

    data["quality_score"] = _quality_score(data)
    data["needs_revision"] = data["quality_score"] < 0.5
    return data


_EXPECTED_FIELDS = {
    "product_page":     ["company", "title", "products"],
    "company_profile":  ["company", "title", "profile"],
    "cover":            ["company", "title"],
    "contact_page":     ["company", "contact"],
    "qr_card":          ["contact"],
    "tech_diagram":     ["title", "systems"],
    "section_divider":  ["title"],
    "price_list":       ["title", "items"],
    "other":            ["title"],
}


def _quality_score(data: dict) -> float:
    """0-1 confidence × completeness × structure heuristic."""
    if data.get("skipped_reason"):
        return 0.0
    conf = float(data.get("classifier_confidence") or 0)
    img_type = data.get("image_type", "other")
    fields = _EXPECTED_FIELDS.get(img_type, ["title"])

    filled = 0
    for f in fields:
        v = data.get(f)
        if v is None or v == "" or v == [] or v == {}:
            continue
        filled += 1
    completeness = filled / max(len(fields), 1)

    # Contact bonus: any messenger/QR raises score
    contact = data.get("contact") or {}
    if isinstance(contact, dict):
        ct_filled = sum(1 for k in ("person", "phone", "email", "website") if contact.get(k))
        contact_bonus = min(ct_filled * 0.05, 0.20)
    else:
        contact_bonus = 0.0

    raw = (data.get("raw_text") or "")
    text_bonus = 0.10 if len(raw) > 30 else 0.0

    score = min(1.0, (conf * 0.40) + (completeness * 0.40) + contact_bonus + text_bonus)
    return round(score, 3)


# GLOBAL across all batches/users. Without this each concurrent batch made its
# own Semaphore(MAX_WORKERS) → 10 users uploading = 10×MAX_WORKERS simultaneous
# vision calls → OpenRouter 429 storm + memory spike. One shared semaphore caps
# total in-flight LLM calls process-wide. Lazily created on the running loop.
_GLOBAL_SEM: "asyncio.Semaphore | None" = None
_CLIENT: "httpx.AsyncClient | None" = None


def _get_sem() -> asyncio.Semaphore:
    global _GLOBAL_SEM
    if _GLOBAL_SEM is None:
        _GLOBAL_SEM = asyncio.Semaphore(config.MAX_WORKERS)
    return _GLOBAL_SEM


def _get_client() -> httpx.AsyncClient:
    """Reused client → connection pooling, no per-batch setup/teardown churn."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(
                max_connections=config.MAX_WORKERS * 2,
                max_keepalive_connections=config.MAX_WORKERS,
            ),
        )
    return _CLIENT


async def extract_batch(images: list, on_progress=None) -> list:
    sem = _get_sem()
    client = _get_client()
    results = []
    tasks = [extract_one(client, img, sem) for img in images]
    for i, coro in enumerate(asyncio.as_completed(tasks)):
        result = await coro
        results.append(result)
        if on_progress:
            on_progress(i + 1, len(images), result.get("source_file", ""))
    return sorted(results, key=lambda x: x.get("source_file", ""))
