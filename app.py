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
import base64

app = Flask(__name__)

ZOOM_SECRET_TOKEN = os.environ.get("ZOOM_SECRET_TOKEN")
ZOOM_ACCOUNT_ID = os.environ.get("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET")
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS")
RECORDINGS_FOLDER_ID = os.environ.get("RECORDINGS_FOLDER_ID")
TRANSCRIPTS_FOLDER_ID = os.environ.get("TRANSCRIPTS_FOLDER_ID")

processed_meetings = set()

def get_zoom_token():
    credentials = base64.b64encode(
        f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()
    ).decode()
    response = requests.post(
        f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}",
        headers={"Authorization": f"Basic {credentials}"}
    )
    return response.json().get("access_token")

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
        body=file_metadata,
        media_body=media,
        supportsAllDrives=True,
        fields="id"
    ).execute()

def download_zoom_file(url, token):
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        allow_redirects=True,
        timeout=300
    )
    return response.content

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("event") == "endpoint.url_validation":
        plain_token = data["payload"]["plainToken"]
        encrypted = hmac.new(
            ZOOM_SECRET_TOKEN.encode(),
            plain_token.encode(),
            hashlib.sha256
        ).hexdigest()
        return jsonify({
            "plainToken": plain_token,
            "encryptedToken": encrypted
        })

    if data.get("event") == "recording.completed":
        payload = data["payload"]["object"]
        topic = payload.get("topic", "")
        meeting_uuid = payload.get("uuid", "")

        if "WinbackEngine" not in topic:
            return jsonify({"status": "filtered"}), 200

        if meeting_uuid in processed_meetings:
            return jsonify({"status": "duplicate"}), 200
        processed_meetings.add(meeting_uuid)

        token = get_zoom_token()
        recording_files = payload.get("recording_files", [])
        start_time = payload.get("start_time", "")[:10]
        filename_base = f"{topic} - {start_time}"

        for file in recording_files:
            file_type = file.get("file_type", "")
            download_url = file.get("download_url", "")
            status = file.get("status", "")

            if status != "completed" or not download_url:
                continue

            if file_type == "MP4":
                content = download_zoom_file(download_url, token)
                upload_to_drive(content, f"{filename_base}.mp4",
                    RECORDINGS_FOLDER_ID, "video/mp4")

            elif file_type in ["TRANSCRIPT", "CC"]:
                content = download_zoom_file(download_url, token)
                upload_to_drive(content, f"{filename_base}.txt",
                    TRANSCRIPTS_FOLDER_ID, "text/plain")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
