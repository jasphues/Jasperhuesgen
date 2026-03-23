import io
import os
from datetime import date
from dateutil.relativedelta import relativedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


def get_drive_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def get_monthly_folder(service):
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_month = first_of_this_month - relativedelta(days=1)
    month_name = last_month.strftime("%Y-%m")  # e.g. "2026-02"

    root_id = get_or_create_folder(service, "Invoices")
    month_id = get_or_create_folder(service, month_name, parent_id=root_id)
    return month_id


def upload_pdf(service, filename, pdf_bytes, folder_id):
    media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf")
    metadata = {"name": filename, "parents": [folder_id]}
    file = service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()
    return file["id"], file.get("webViewLink", "")
