import base64
import os
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("gmail", "v1", credentials=creds)


def get_previous_month_range():
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - relativedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return last_month_start, last_month_end


def search_invoice_emails(service):
    start, end = get_previous_month_range()
    after = start.strftime("%Y/%m/%d")
    before = (end + relativedelta(days=1)).strftime("%Y/%m/%d")

    # Strict subject-only search to avoid pulling in non-invoice PDFs
    query = (
        f"(subject:invoice OR subject:rechnung OR subject:receipt OR subject:faktura "
        f"OR subject:ausgangsrechnung "
        f"OR subject:\"your invoice\" OR subject:\"ihre rechnung\" OR subject:\"your receipt\") "
        f"has:attachment filename:pdf "
        f"after:{after} before:{before}"
    )

    result = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    return result.get("messages", [])


def download_pdf_attachments(service, message_id):
    """Returns list of (filename, pdf_bytes, subject, sender) tuples."""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
    subject = headers.get("subject", "No Subject")
    sender = headers.get("from", "Unknown Sender")

    pdfs = []
    parts = _get_parts(msg["payload"])
    for part in parts:
        filename = part.get("filename", "")
        mime = part.get("mimeType", "")
        if not filename.lower().endswith(".pdf") and mime != "application/pdf":
            continue

        attachment_id = part.get("body", {}).get("attachmentId")
        data = part.get("body", {}).get("data")

        if attachment_id:
            att = service.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute()
            data = att["data"]

        if data:
            pdf_bytes = base64.urlsafe_b64decode(data)
            pdfs.append((filename or f"invoice_{message_id}.pdf", pdf_bytes, subject, sender))

    return pdfs


def _get_parts(payload):
    parts = []
    if "parts" in payload:
        for part in payload["parts"]:
            parts.extend(_get_parts(part))
    else:
        parts.append(payload)
    return parts
