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


def upload_file(pdf_bytes: bytes, filename: str) -> str:
    """Upload PDF and return documentFileId."""
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
        return r.json()["documentFileId"]
    raise Exception("upload_file failed after 3 retries")


def create_voucher_draft(
    vendor_name: str,
    voucher_date: str,
    amount_gross: float,
    category_id: str | None,
    vat_type: str,
    vat_rate: int,
    document_file_id: str,
    description: str,
    notes: str = "",
) -> str:
    """Create a draft voucher and return its ID."""

    line_item = {
        "type": "custom",
        "name": description,
        "quantity": 1,
        "unitPrice": {
            "currency": "EUR",
            "grossAmount": round(amount_gross, 2),
            "taxRatePercentage": vat_rate,
        },
    }
    if category_id:
        line_item["categoryId"] = category_id

    body = {
        "voucherDate": voucher_date,
        "address": {"name": vendor_name},
        "lineItems": [line_item],
        "totalPrice": {"currency": "EUR"},
        "taxConditions": {"taxType": vat_type},
        "files": [{"documentFileId": document_file_id}],
    }

    if notes:
        body["remark"] = notes

    result = _post("/vouchers", json=body)
    return result["id"]


def find_existing_voucher(vendor_name: str, date_from: str, date_to: str) -> list:
    """Search for existing vouchers — skipped for now to avoid API errors."""
    return []
