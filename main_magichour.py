"""
Video Generator - Main Script
สแกน Google Drive หาวิดีโอต้นฉบับ → Generate วิดีโอใหม่ด้วย Magic Hour API → Upload กลับ Google Drive
"""

import os
import time
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import tempfile

# ==================== CONFIG ====================
SOURCE_FOLDER_ID  = os.environ.get("GDRIVE_SOURCE_FOLDER_ID")
OUTPUT_FOLDER_ID  = os.environ.get("GDRIVE_OUTPUT_FOLDER_ID")
MAGIC_HOUR_KEY    = os.environ.get("MAGIC_HOUR_API_KEY")
GDRIVE_CREDENTIALS = os.environ.get("GDRIVE_CREDENTIALS_JSON")

MAGIC_HOUR_BASE   = "https://api.magichour.ai/api/developer/v1"

PROMPT = (
    "A beautiful young Thai woman, elegant and attractive, "
    "holding and showcasing the product with a bright smile, "
    "same product as original video, same action and movements, "
    "clean bright background, natural studio lighting, "
    "vertical video format for TikTok/Reels/Shorts, "
    "professional product showcase style, high quality"
)

# ==================== LOGGING ====================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/run_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ==================== GOOGLE DRIVE ====================
def get_drive_service():
    creds_dict = json.loads(GDRIVE_CREDENTIALS)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def list_videos_in_folder(service, folder_id):
    log.info(f"กำลังสแกน folder...")
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'video/' and trashed=false",
        fields="files(id, name, size)"
    ).execute()
    files = results.get("files", [])
    log.info(f"พบวิดีโอ {len(files)} ไฟล์")
    return files

def download_video(service, file_id, file_name, tmp_dir):
    log.info(f"Downloading: {file_name}")
    request = service.files().get_media(fileId=file_id)
    file_path = os.path.join(tmp_dir, file_name)
    with open(file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    log.info(f"Downloaded: {file_name}")
    return file_path

def upload_video(service, file_path, folder_id, file_name):
    log.info(f"Uploading to Drive: {file_name}")
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id, name"
    ).execute()
    log.info(f"Uploaded: {file['name']} (ID: {file['id']})")
    return file

# ==================== MAGIC HOUR API ====================
def get_upload_url(file_name):
    """ขอ pre-signed URL สำหรับ upload วิดีโอต้นฉบับ"""
    headers = {"Authorization": f"Bearer {MAGIC_HOUR_KEY}", "Content-Type": "application/json"}
    resp = requests.post(
        f"{MAGIC_HOUR_BASE}/asset-storage",
        headers=headers,
        json={"files": [{"name": file_name, "type": "video/mp4"}]}
    )
    resp.raise_for_status()
    data = resp.json()
    return data["files"][0]["uploadUrl"], data["files"][0]["downloadUrl"]

def upload_to_magic_hour(file_path, file_name):
    """Upload วิดีโอต้นฉบับไปที่ Magic Hour storage"""
    log.info(f"Getting upload URL from Magic Hour...")
    upload_url, download_url = get_upload_url(file_name)
    log.info(f"Uploading to Magic Hour storage...")
    with open(file_path, "rb") as f:
        put_resp = requests.put(upload_url, data=f, headers={"Content-Type": "video/mp4"})
        put_resp.raise_for_status()
    log.info(f"Uploaded to Magic Hour: {download_url}")
    return download_url

def create_video_job(video_url):
    """สร้าง video-to-video job ใน Magic Hour"""
    headers = {"Authorization": f"Bearer {MAGIC_HOUR_KEY}", "Content-Type": "application/json"}
    payload = {
        "video_source": {"type": "url", "url": video_url},
        "prompt": PROMPT,
        "style": "realistic",
        "output_format": "mp4",
        "aspect_ratio": "9:16",
        "duration": 5
    }
    resp = requests.post(
        f"{MAGIC_HOUR_BASE}/video-to-video",
        headers=headers,
        json=payload
    )
    resp.raise_for_status()
    job_id = resp.json()["id"]
    log.info(f"Job created: {job_id}")
    return job_id

def wait_for_job(job_id, timeout=600):
    """รอจนกว่า job จะเสร็จ"""
    headers = {"Authorization": f"Bearer {MAGIC_HOUR_KEY}"}
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{MAGIC_HOUR_BASE}/video-projects/{job_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        log.info(f"  Status: {status}")
        if status == "complete":
            return data["downloads"][0]["url"]
        elif status in ("failed", "error"):
            raise Exception(f"Job failed: {data}")
        time.sleep(15)
    raise Exception("Timeout waiting for video generation")

def download_generated_video(video_url, output_path):
    log.info(f"Downloading generated video...")
    response = requests.get(video_url, stream=True)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    log.info(f"Saved: {output_path}")

# ==================== MAIN ====================
def main():
    log.info("=" * 50)
    log.info(f"Video Generator เริ่มทำงาน: {datetime.now()}")
    log.info("=" * 50)

    service = get_drive_service()
    source_videos = list_videos_in_folder(service, SOURCE_FOLDER_ID)

    if not source_videos:
        log.warning("ไม่พบวิดีโอใน source folder")
        return

    success_count = 0
    fail_count = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        for video in source_videos:
            video_name = video["name"]
            video_id   = video["id"]
            log.info(f"\n{'─'*40}")
            log.info(f"Processing: {video_name}")

            try:
                # 1. Download จาก Google Drive
                source_path = download_video(service, video_id, video_name, tmp_dir)

                # 2. Upload ไปที่ Magic Hour
                mh_url = upload_to_magic_hour(source_path, video_name)

                # 3. สร้าง generation job
                job_id = create_video_job(mh_url)

                # 4. รอผลลัพธ์
                output_name = f"generated_{Path(video_name).stem}_{datetime.now().strftime('%Y%m%d')}.mp4"
                generated_url = wait_for_job(job_id)

                # 5. Download วิดีโอที่ generate แล้ว
                output_path = os.path.join(tmp_dir, output_name)
                download_generated_video(generated_url, output_path)

                # 6. Upload ขึ้น Google Drive output folder
                upload_video(service, output_path, OUTPUT_FOLDER_ID, output_name)

                success_count += 1
                log.info(f"สำเร็จ: {video_name} → {output_name}")

            except Exception as e:
                fail_count += 1
                log.error(f"Error processing {video_name}: {str(e)}")
                continue

    log.info(f"\n{'='*50}")
    log.info(f"เสร็จสิ้น! สำเร็จ: {success_count} | ล้มเหลว: {fail_count}")
    log.info(f"{'='*50}")

if __name__ == "__main__":
    main()
