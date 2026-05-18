"""Multi-agent extraction: Classifier → Specialized Agent per image type."""

CLASSIFIER_PROMPT = """Look at this image and classify it into exactly ONE type.
Return ONLY a JSON: {"image_type": "<type>", "confidence": 0.0-1.0}

Types:
- product_page: shows products with names, models, specs, prices
- company_profile: about the company, factory, history, certifications
- cover: front/back cover of a brochure or catalog
- contact_page: contact info, addresses, phone numbers, QR codes
- qr_card: business card or small panel dominated by one or more QR codes (WeChat, LINE, WhatsApp) with adjacent printed handles, IDs, names, or phone numbers
- tech_diagram: architecture diagrams, system layouts, flowcharts
- section_divider: chapter/section title page with minimal content
- price_list: tables of prices, rates, fees
- other: anything that doesn't fit above"""

AGENT_PROMPTS = {
    "product_page": """Extract ALL products from this catalog page.
Return JSON:
{
  "company": "company name or null",
  "title": "page title",
  "products": [
    {
      "name": "product name",
      "model": "model number or null",
      "specs": "dimensions, material, capacity, etc.",
      "category": "product category",
      "price": "price if shown or null",
      "image_desc": "brief description of what the product looks like"
    }
  ],
  "raw_text": "all text on the image exactly as shown"
}
Extract EVERY product. Include all specs, dimensions, materials visible.""",

    "company_profile": """Extract company information from this image.
Return JSON:
{
  "company": "full company name",
  "title": "page title",
  "profile": {
    "description": "what the company does",
    "established": "year or null",
    "location": "city, country",
    "factory_details": "machines, capacity, area if mentioned",
    "certifications": ["list of certifications"],
    "key_services": ["list of services offered"]
  },
  "contact": {"person": null, "phone": null, "email": null, "website": null, "address": null},
  "raw_text": "all text on the image exactly as shown"
}""",

    "cover": """Extract all information from this brochure/catalog cover.
Return JSON:
{
  "company": "company name",
  "title": "brochure title or tagline",
  "contact": {"person": null, "phone": null, "email": null, "website": null, "address": null},
  "key_info": ["taglines, slogans, booth numbers, trade show info"],
  "raw_text": "all text on the image exactly as shown"
}""",

    "contact_page": """Extract ALL contact information from this image.
Return JSON:
{
  "company": "company name",
  "title": "page title",
  "contact": {
    "person": "contact person name or null",
    "phone": "phone number(s)",
    "email": "email address(es)",
    "website": "website URL(s)",
    "address": "full address"
  },
  "offices": [{"region": "...", "address": "...", "phone": "...", "email": "..."}],
  "raw_text": "all text on the image exactly as shown"
}""",

    "tech_diagram": """Extract technical/architectural information from this diagram.
Return JSON:
{
  "company": "company name or null",
  "title": "diagram title",
  "systems": [
    {"name": "system/component name", "zone": "where deployed", "description": "what it does", "features": ["list"]}
  ],
  "architecture": "overall description of how the systems connect",
  "key_info": ["important technical facts"],
  "raw_text": "all text on the image exactly as shown"
}""",

    "section_divider": """Extract section information from this divider page.
Return JSON:
{
  "company": "company name or null",
  "title": "section title",
  "section_number": "section number if shown",
  "key_info": ["any visible details"],
  "raw_text": "all text on the image exactly as shown"
}""",

    "price_list": """Extract all pricing information from this image.
Return JSON:
{
  "company": "company name or null",
  "title": "page title",
  "items": [
    {"name": "item name", "model": "model or null", "price": "price", "unit": "per unit/kg/etc", "specs": "any specs"}
  ],
  "currency": "currency if shown",
  "raw_text": "all text on the image exactly as shown"
}""",

    "qr_card": """This image contains one or more QR codes with printed contact info NEAR each code.
Carefully read every label adjacent to a QR code: WeChat ID (`微信号:` / `WeChat:` / `WeChat ID:`),
LINE ID (`LINE ID:` / `LINE:`), WhatsApp number (`WhatsApp:` / `WA:`), Viber, Telegram, KakaoTalk ID,
person name, company name, job title, phone, email, website.

Return JSON:
{
  "company": "company name or null",
  "title": "card/page title or null",
  "contact": {
    "person": "name printed on the card or null",
    "phone": "primary phone number or null",
    "email": "email or null",
    "wechat_id": "WeChat ID printed near QR (after 微信号 / WeChat) or null",
    "line_id": "LINE ID printed near QR or null",
    "whatsapp": "WhatsApp number printed near QR or null",
    "website": "website URL or null",
    "address": "address or null"
  },
  "key_info": ["other handles, IDs, booth numbers, taglines"],
  "raw_text": "all text on the image exactly as shown"
}
Read ONLY printed text — do NOT invent IDs from the QR pattern. Preserve original casing of handles.""",

    "other": """Extract all information visible in this image.
Return JSON:
{
  "company": "company name or null",
  "title": "description of what the image shows",
  "key_info": ["all important facts"],
  "raw_text": "all text on the image exactly as shown"
}""",
}
