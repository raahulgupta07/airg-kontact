"""Parse currency code + numeric amount from a free-form price string.

Examples handled:
  "$4,850 USD"       -> ("USD", 4850.0)
  "€ 1.234,50"       -> ("EUR", 1234.50)
  "RMB 12,000"       -> ("CNY", 12000.0)
  "¥120,000"         -> ("JPY", 120000.0)  (heuristic ambiguity w/ CNY: prefer JPY when whole number)
  "from £55.00"      -> ("GBP", 55.0)
  "₹999/-"           -> ("INR", 999.0)
"""
from __future__ import annotations

import re
from typing import Optional

_SYMBOL_CCY = {
    "$": "USD", "US$": "USD", "C$": "CAD", "A$": "AUD", "S$": "SGD",
    "HK$": "HKD", "NT$": "TWD",
    "€": "EUR", "£": "GBP", "₹": "INR", "₩": "KRW",
    "¥": "JPY",  # collides w/ CNY 元; refined below
    "₽": "RUB", "฿": "THB", "₫": "VND",
    "R$": "BRL", "Mex$": "MXN",
}

# ISO codes / common written forms (case insensitive)
_WORD_CCY = {
    "USD": "USD", "US": "USD",
    "EUR": "EUR",
    "GBP": "GBP",
    "JPY": "JPY", "YEN": "JPY",
    "CNY": "CNY", "RMB": "CNY", "YUAN": "CNY", "元": "CNY", "人民币": "CNY",
    "INR": "INR", "RS": "INR", "RUPEE": "INR", "RUPEES": "INR",
    "AUD": "AUD", "CAD": "CAD", "SGD": "SGD", "HKD": "HKD",
    "KRW": "KRW", "WON": "KRW",
    "TWD": "TWD", "NTD": "TWD",
    "RUB": "RUB", "THB": "THB", "VND": "VND", "BRL": "BRL", "MXN": "MXN",
    "CHF": "CHF", "SEK": "SEK", "NOK": "NOK", "DKK": "DKK",
}


def parse_price(text: str) -> tuple[Optional[str], Optional[float]]:
    """Return (currency_iso, amount) or (None, None) if unparseable."""
    if not text or not isinstance(text, str):
        return None, None
    s = text.strip()
    upper = s.upper()

    currency: Optional[str] = None

    # 1) symbol prefix or suffix (longest first to catch HK$/C$/...)
    for sym in sorted(_SYMBOL_CCY, key=len, reverse=True):
        if sym in s:
            currency = _SYMBOL_CCY[sym]
            break

    # 2) word/ISO code
    if currency is None or currency == "JPY":  # disambiguate ¥
        m = re.search(r"\b(USD|EUR|GBP|JPY|YEN|CNY|RMB|YUAN|INR|RS|RUPEES?|AUD|CAD|SGD|HKD|KRW|WON|TWD|NTD|RUB|THB|VND|BRL|MXN|CHF|SEK|NOK|DKK)\b", upper)
        if m:
            currency = _WORD_CCY[m.group(1)]
        elif "元" in s or "人民币" in s:
            currency = "CNY"

    # 3) Extract numeric amount
    # Find longest numeric chunk with optional thousand separators + decimal
    # Handle both "1,234.56" (US) and "1.234,56" (EU)
    num_str = None
    for m in re.finditer(r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?", s):
        if num_str is None or len(m.group()) > len(num_str):
            num_str = m.group()

    if num_str is None:
        return currency, None

    # Decide decimal separator
    n = num_str.replace(" ", "")
    if "," in n and "." in n:
        # Last separator wins as decimal
        if n.rfind(",") > n.rfind("."):
            n = n.replace(".", "").replace(",", ".")
        else:
            n = n.replace(",", "")
    elif "," in n:
        # If group of 3 digits after comma, treat as thousands; else decimal
        parts = n.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            n = parts[0] + "." + parts[1]
        else:
            n = "".join(parts)

    try:
        amount = float(n)
    except ValueError:
        amount = None

    return currency, amount
