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

    # vCard overlay — authoritative
    for qr in qr_codes:
        if qr.get("type") == "vcard":
            vcard = qr.get("parsed") or {}
            for k, v in vcard.items():
                if v:
                    contact[k] = v
            if vcard.get("company") and not data.get("company"):
                data["company"] = vcard["company"]

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
                return _parse_json(r.json()["choices"][0]["message"]["content"])
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
    # The LLM may also produce a 'metadata' field; loader metadata takes precedence
    # for technical fields, LLM fields are kept for anything not in loader meta.
    if isinstance(meta, dict):
        existing_meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        merged = dict(existing_meta)
        for k, v in meta.items():
            if v is not None:
                merged[k] = v
        data["metadata"] = merged

    return data


async def extract_batch(images: list, on_progress=None) -> list:
    sem = asyncio.Semaphore(config.MAX_WORKERS)
    results = []
    async with httpx.AsyncClient() as client:
        tasks = [extract_one(client, img, sem) for img in images]
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            results.append(result)
            if on_progress:
                on_progress(i + 1, len(images), result.get("source_file", ""))
    return sorted(results, key=lambda x: x.get("source_file", ""))
