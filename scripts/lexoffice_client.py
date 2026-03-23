import os
import time
import requests

BASE_URL = "https://api.lexware.io/v1"


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['LEXOFFICE_API_KEY']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _get(path, params=None, retries=3):
    for attempt in range(retries):
        r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise Exception(f"GET {path} failed after {retries} retries")


def _post(path, json=None, files=None, retries=3):
    for attempt in range(retries):
        if files:
            headers = {k: v for k, v in _headers().items() if k != "Content-Type"}
            r = requests.post(f"{BASE_URL}{path}", headers=headers, files=files)
        else:
            r = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=json)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if not r.ok:
            raise Exception(f"{r.status_code} {r.reason} for url: {r.url} — {r.text}")
        return r.json()
    raise Exception(f"POST {path} failed after {retries} retries")


def get_posting_categories():
    result = _get("/posting-categories")
    if isinstance(result, list):
        return result
    return result.get("content", [])


def upload_file_and_get_voucher_id(pdf_bytes: bytes, filename: str) -> tuple[str, str]:
    """Upload PDF, returns (file_id, voucher_id) — Lex Office auto-creates a draft voucher."""
    headers = {k: v for k, v in _headers().items() if k != "Content-Type"}
    for attempt in range(3):
        r = requests.post(
            f"{BASE_URL}/files",
            headers=headers,
            params={"type": "voucher"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
        )
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if not r.ok:
            raise Exception(f"{r.status_code} {r.reason} for url: {r.url} — {r.text}")
        data = r.json()
        return data["id"], data["voucherId"]
    raise Exception("upload_file failed after 3 retries")


def update_voucher_draft(
    voucher_id: str,
    vendor_name: str,
    voucher_date: str,
    amount_gross: float,
    category_id: str | None,
    vat_type: str,
    vat_rate: int,
    description: str,
    notes: str = "",
) -> str | None:
    """Update an existing draft voucher with invoice details.
    Returns voucher ID, or None if voucher should be skipped."""

    current = _get(f"/vouchers/{voucher_id}")
    version = current.get("version", 0)
    status = current.get("voucherStatus", "")
    voucher_type = current.get("type", "purchaseinvoice")

    # Skip already-processed or outgoing invoices
    if status in ("paid", "paidoff", "voided"):
        print(f"  Skipping — voucher already {status} in Lex Office")
        return None
    if voucher_type == "salesinvoice":
        print(f"  Skipping — outgoing sales invoice, not an expense")
        return None

    # Calculate tax amount
    if vat_type == "gross" and vat_rate > 0:
        tax_amount = round(amount_gross * vat_rate / (100 + vat_rate), 2)
    else:
        tax_amount = 0.0

    # Fall back to existing category if we couldn't detect one
    existing_items = current.get("voucherItems", [])
    fallback_category = existing_items[0].get("categoryId") if existing_items else None
    effective_category = category_id or fallback_category

    voucher_item = {
        "amount": round(amount_gross, 2),
        "taxAmount": tax_amount,
        "taxRatePercent": float(vat_rate),
        "categoryId": effective_category,
    }

    final_items = [voucher_item] if effective_category else existing_items
    if not final_items:
        print(f"  Skipping update — no voucherItems could be determined, file attached to draft in Lex Office")
        return voucher_id  # file is attached, user fills in manually

    body = {
        "version": version,
        "type": voucher_type,
        "voucherNumber": current.get("voucherNumber", ""),
        "voucherDate": voucher_date,
        "taxType": vat_type,
        "totalGrossAmount": round(amount_gross, 2),
        "totalTaxAmount": tax_amount,
        "voucherItems": final_items,
    }

    # Preserve contact info from existing voucher
    if current.get("contactId"):
        body["contactId"] = current["contactId"]
    elif current.get("useCollectiveContact"):
        body["useCollectiveContact"] = True
        if current.get("contactName"):
            body["contactName"] = current["contactName"]
    elif vendor_name:
        body["useCollectiveContact"] = True
        body["contactName"] = vendor_name

    if notes:
        body["remark"] = notes

    for attempt in range(3):
        r = requests.put(
            f"{BASE_URL}/vouchers/{voucher_id}",
            headers=_headers(),
            json=body,
        )
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if not r.ok:
            raise Exception(f"{r.status_code} {r.reason} for url: {r.url} — {r.text}")
        return voucher_id
    raise Exception("update_voucher_draft failed after 3 retries")


def find_existing_voucher(vendor_name: str, date_from: str, date_to: str) -> list:
    """Search for existing vouchers — skipped for now to avoid API errors."""
    return []
