import os
import httpx
import asyncio
from functools import lru_cache

_GEOCODE_CACHE = {}
_LAST_CALL_TS = [0.0]
_RATE_LIMIT_SEC = 1.0  # Nominatim limit

USER_AGENT = "city-kontact/1.0 (admin@kontact.local)"


async def reverse_geocode(lat: float, lng: float) -> dict:
    if lat is None or lng is None:
        return {}
    key = f"{round(lat,4)},{round(lng,4)}"
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]
    # Rate limit
    import time
    now = time.time()
    wait = _RATE_LIMIT_SEC - (now - _LAST_CALL_TS[0])
    if wait > 0:
        await asyncio.sleep(wait)
    _LAST_CALL_TS[0] = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            r = await cx.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lng, "format": "json", "zoom": 14},
                headers={"User-Agent": USER_AGENT},
            )
            if r.status_code != 200:
                return {}
            j = r.json()
            addr = j.get("address", {})
            out = {
                "country": addr.get("country"),
                "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county"),
                "address_full": j.get("display_name"),
            }
            _GEOCODE_CACHE[key] = out
            return out
    except Exception:
        return {}
