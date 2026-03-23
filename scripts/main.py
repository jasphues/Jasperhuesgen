"""
Invoice Automation — runs on the 5th of each month via GitHub Actions.
1. Searches Gmail for invoices from the previous month
2. Downloads PDF attachments → uploads to Google Drive
3. Creates draft vouchers in Lex Office with auto-categorization
"""

import re
import sys
from datetime import date
from dateutil.relativedelta import relativedelta

import pdfplumber

from gmail_client import get_gmail_service, search_invoice_emails, download_pdf_attachments
from drive_client import get_drive_service, get_monthly_folder, upload_pdf
from lexoffice_client import (
    get_posting_categories,
    upload_file_and_get_voucher_id,
    update_voucher_draft,
    find_existing_voucher,
)
from categorizer import categorize, match_category_id


def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import io
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return ""


def extract_amount(pdf_text: str) -> float | None:
    """Try to extract total gross amount from PDF text."""
    # Look for patterns like "Total: 99,00 EUR" or "Gesamt: 99.00 €"
    patterns = [
        r"(?:total|gesamt|summe|betrag|amount)[^\d]{0,30}([\d]{1,6}[.,]\d{2})\s*(?:eur|€)?",
        r"([\d]{1,6}[.,]\d{2})\s*(?:eur|€)\s*$",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, pdf_text.lower())
        if matches:
            raw = matches[-1].replace(",", ".").replace(" ", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def format_iso_date(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00.000+01:00")


def get_previous_month_iso():
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - relativedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return (
        last_month_start.strftime("%Y-%m-%d"),
        last_month_end.strftime("%Y-%m-%d"),
    )


def main():
    print("=== Invoice Automation Starting ===")

    gmail = get_gmail_service()
    drive = get_drive_service()

    posting_categories = get_posting_categories()
    print(f"Loaded {len(posting_categories)} Lex Office posting categories")

    drive_folder_id = get_monthly_folder(drive)
    print(f"Google Drive folder ready: {drive_folder_id}")

    messages = search_invoice_emails(gmail)
    print(f"Found {len(messages)} invoice emails")

    date_from, date_to = get_previous_month_iso()
    processed = 0
    skipped = 0
    errors = []

    for msg in messages:
        try:
            pdfs = download_pdf_attachments(gmail, msg["id"])
            if not pdfs:
                continue

            for filename, pdf_bytes, subject, sender in pdfs:
                print(f"\nProcessing: {filename} | From: {sender} | Subject: {subject}")

                # Extract sender name and email
                sender_name_match = re.match(r"^(.*?)\s*<", sender)
                sender_name = sender_name_match.group(1).strip() if sender_name_match else sender
                sender_email_match = re.search(r"<(.+?)>", sender)
                sender_email = sender_email_match.group(1) if sender_email_match else sender

                # Extract PDF text
                pdf_text = extract_pdf_text(pdf_bytes)

                # Categorize
                cat_result = categorize(sender_email, sender_name, subject, pdf_text)
                category_id = match_category_id(cat_result["category_hint"], posting_categories)
                print(f"  Category hint: {cat_result['category_hint']} → ID: {category_id}")
                print(f"  VAT: {cat_result['vat_type']} {cat_result['vat_rate']}% {cat_result['notes']}")

                # Extract amount
                amount = extract_amount(pdf_text)
                if not amount:
                    amount = 0.0
                    print("  Warning: Could not extract amount — set to 0.00, please update manually")

                # Check for duplicates in Lex Office
                existing = find_existing_voucher(sender_name, date_from, date_to)
                if existing:
                    print(f"  Possible duplicate found in Lex Office — skipping: {[v.get('voucherNumber') for v in existing]}")
                    skipped += 1
                    continue

                # Upload PDF to Google Drive
                drive_file_id, drive_link = upload_pdf(drive, filename, pdf_bytes, drive_folder_id)
                print(f"  Uploaded to Drive: {drive_link}")

                # Upload PDF to Lex Office — auto-creates a draft voucher
                lex_file_id, voucher_id = upload_file_and_get_voucher_id(pdf_bytes, filename)

                # Update the draft voucher with invoice details
                voucher_id = update_voucher_draft(
                    voucher_id=voucher_id,
                    vendor_name=sender_name,
                    voucher_date=format_iso_date(date.today().replace(day=1) - relativedelta(days=1)),
                    amount_gross=amount,
                    category_id=category_id,
                    vat_type=cat_result["vat_type"],
                    vat_rate=cat_result["vat_rate"],
                    description=subject[:255],
                    notes=cat_result["notes"],
                )
                print(f"  Updated draft voucher: {voucher_id}")
                processed += 1

        except Exception as e:
            errors.append(f"{msg['id']}: {e}")
            print(f"  ERROR: {e}")

    print(f"\n=== Done: {processed} vouchers created, {skipped} skipped, {len(errors)} errors ===")
    if errors:
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
