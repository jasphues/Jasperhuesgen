"""
Keyword-based expense categorizer.
Determines posting category and VAT status from invoice text / sender / subject.
"""

import re

# Maps category keywords → Lex Office posting category name fragments
# These are matched against sender email, sender name, and subject (all lowercased)
CATEGORY_RULES = [
    # Office rent
    (["myspace", "my space", "regus", "wework", "spaces", "rent", "miete", "büro", "buro", "office rent"], "office rent"),
    # Software / licenses
    (["adobe", "github", "gitlab", "figma", "notion", "slack", "zoom", "microsoft", "google workspace",
      "jetbrains", "linear", "vercel", "aws", "amazon web", "digitalocean", "heroku", "netlify",
      "stripe", "twilio", "sendgrid", "openai", "anthropic", "license", "lizenz", "subscription",
      "software", "saas", "cloud", "hosting", "domain", "namecheap", "godaddy", "cloudflare"], "license"),
    # Travel
    (["lufthansa", "ryanair", "easyjet", "db bahn", "bahn", "flug", "hotel", "airbnb", "booking.com",
      "travel", "reise", "taxi", "uber", "freenow", "mietwagen"], "travel"),
    # Marketing / advertising
    (["google ads", "facebook ads", "meta ads", "linkedin ads", "instagram", "marketing",
      "werbung", "advertising", "canva", "mailchimp", "hubspot"], "marketing"),
    # Telecommunications
    (["telekom", "vodafone", "o2", "1&1", "telefon", "mobile", "internet", "sim"], "telecommunications"),
    # Insurance
    (["versicherung", "insurance", "allianz", "axa", "signal iduna", "hdi"], "insurance"),
    # Office supplies
    (["amazon", "otto", "staples", "bürobedarf", "office supplies", "paper", "papier"], "office supplies"),
    # Accounting / legal
    (["steuerberater", "notar", "rechtsanwalt", "datev", "lexoffice", "sevdesk", "buchhaltung",
      "accounting", "auditor", "legal"], "accounting"),
]

# VAT patterns in PDF text
VAT_PATTERNS = [
    r"19\s*%\s*(mwst|mwst\.|mehrwertsteuer|ust|ust\.|umsatzsteuer|vat)",
    r"(mwst|mwst\.|mehrwertsteuer|ust|ust\.|umsatzsteuer|vat)[^0-9]{0,20}19\s*%",
    r"7\s*%\s*(mwst|mwst\.|mehrwertsteuer|ust|ust\.|umsatzsteuer|vat)",
    r"(mwst|mwst\.|mehrwertsteuer|ust|ust\.|umsatzsteuer|vat)[^0-9]{0,20}7\s*%",
]

REVERSE_CHARGE_PATTERNS = [
    r"reverse\s*charge",
    r"steuerschuldnerschaft\s+des\s+leistungsempf",
    r"§\s*13b",
]

VAT_FREE_PATTERNS = [
    r"steuerfreie?\s+leis",
    r"§\s*4\s+nr",
    r"innergemeinschaftliche?\s+lief",
    r"0\s*%\s*(mwst|vat|ust)",
]


def categorize(sender_email: str, sender_name: str, subject: str, pdf_text: str) -> dict:
    """
    Returns dict with:
      - category_hint: str (fragment to match against Lex Office category names)
      - vat_type: "gross" | "net" | "vatfree"
      - vat_rate: 19 | 7 | 0
      - notes: str
    """
    combined = f"{sender_email} {sender_name} {subject}".lower()
    pdf_lower = pdf_text.lower() if pdf_text else ""

    # Determine category
    category_hint = "other"
    for keywords, cat in CATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            category_hint = cat
            break

    # Determine VAT
    vat_rate = 0
    vat_type = "vatfree"
    notes = ""

    if any(re.search(p, pdf_lower) for p in REVERSE_CHARGE_PATTERNS):
        vat_type = "vatfree"
        notes = "Reverse charge / §13b"
    elif any(re.search(p, pdf_lower) for p in VAT_FREE_PATTERNS):
        vat_type = "vatfree"
        notes = "VAT-free"
    else:
        for pattern in VAT_PATTERNS:
            m = re.search(pattern, pdf_lower)
            if m:
                # extract rate from match context
                rate_match = re.search(r"(19|7)\s*%", m.group(0))
                if rate_match:
                    vat_rate = int(rate_match.group(1))
                else:
                    vat_rate = 19  # default
                vat_type = "gross"
                break

        if vat_rate == 0 and not any(re.search(p, pdf_lower) for p in VAT_FREE_PATTERNS):
            # foreign invoice (no German VAT found) — treat as net, vatfree
            vat_type = "vatfree"
            notes = "No German VAT detected — possibly foreign invoice"

    return {
        "category_hint": category_hint,
        "vat_type": vat_type,
        "vat_rate": vat_rate,
        "notes": notes,
    }


def match_category_id(category_hint: str, posting_categories: list) -> str | None:
    """Match category hint to actual Lex Office posting category ID."""
    hint = category_hint.lower()
    for cat in posting_categories:
        name = cat.get("name", "").lower()
        if hint in name or name in hint:
            return cat["id"]
    # fallback: partial word match
    for cat in posting_categories:
        name = cat.get("name", "").lower()
        for word in hint.split():
            if word in name:
                return cat["id"]
    return None
