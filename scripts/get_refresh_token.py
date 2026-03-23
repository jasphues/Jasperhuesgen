"""
Run this ONCE locally to generate your Google OAuth refresh token.
Usage:
    python get_refresh_token.py path/to/client_secret.json
"""

import json
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

if len(sys.argv) < 2:
    print("Usage: python get_refresh_token.py path/to/client_secret.json")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== Copy these to your GitHub Secrets ===")
print(f"GOOGLE_CLIENT_ID:     {creds.client_id}")
print(f"GOOGLE_CLIENT_SECRET: {creds.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN: {creds.refresh_token}")
