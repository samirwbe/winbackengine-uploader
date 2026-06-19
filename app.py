import os
import requests
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import json
import hmac
import hashlib

app = Flask(__name__)

ZOOM_SECRET_TOKEN = os.environ.get("ZOOM_SECRET_TOKEN")
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS")
RECORDINGS_FOLDER_ID = os.environ.get("RECORDINGS_FOLDER_ID")
TRANSCRIPTS_FOLDER_ID = os.environ.get("TRANSCRIPTS_FOLDER_ID")

processed_meetings = set()

def get_drive_service():
    creds_dict = json.loads(GOOGLE_CREDS)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def upload_to_drive(file_content, filename, folder_id, mimetype):
    service = get_drive_service()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype=mimetype)
    service.files().create(
