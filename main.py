"""
Video Generator - Main Script
สแกน Google Drive หาวิดีโอต้นฉบับ → Generate วิดีโอใหม่ด้วย fal.ai → Upload กลับ Google Drive
"""

import os
import time
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
import fal_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
import tempfile

# ==================== CONFIG ====================
SOURCE_FOLDER_ID = os.environ.get("GDRIVE_SOURCE_FOLDER_ID")   # Google Drive folder ID ต้นฉบับ
OUTPUT_FOLDER_ID = os.environ.get("GDRIVE_OUTPUT_FOLDER_ID")   # Google Drive folder ID output
FAL_KEY = os.environ.get("FAL_KEY")                            # fal.ai API key
GDRIVE_CREDENTIALS = os.environ.get("GDRIVE_CREDENTIALS_JSON") # Google Service Account JSON

# Video generation prompt
PROMPT_TEMPLATE = """
A beautiful young Thai woman, elegant and attractive, 
holding and showcasing the product with a bright smile,
same product as original video, same action and movements,
clean bright background, natural studio lighting,
vertical video format for TikTok/Reels/Shorts,
professional product showcase style, high quality
"""

# ==================== LOGGING ====================
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
    """สร้าง Google Drive service จาก Service Account"""
    creds_dict = json.loads(GDRIVE_CREDENTIALS)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def list_videos_in_folder(service, folder_id):
    """ดึงรายการไฟล์วิดีโอใน Google Drive folder"""
    log.info(f"📂 กำลังสแกน folder: {folder_id}")
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'video/' and trashed=false",
        fields="files(id, name, size)"
    ).execute()
    files = results.get("files", [])
    log.info(f"✅ พบวิดีโอ {len(files)} ไฟล์")
    return files

def download_video(service, file_id, file_name, tmp_dir):
    """Download วิดีโอจาก Google Drive"""
    log.info(f"⬇️  Downloading: {file_name}")
    request = service.files().get_media(fileId=file_id)
    file_path = os.path.join(tmp_dir, file_name)
    with open(file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    log.info(f"✅ Downloaded: {file_name}")
    return file_path

def upload_video(service, file_path, folder_id, file_name):
    """Upload วิดีโอขึ้น Google Drive"""
    log.info(f"⬆️  Uploading: {file_name}")
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id, name"
    ).execute()
    log.info(f"✅ Uploaded: {file['name']} (ID: {file['id']})")
    return file

# ==================== FAL.AI VIDEO GENERATION ====================
def upload_video_to_fal(video_path):
    """Upload วิดีโอต้นฉบับไปที่ fal.ai"""
    log.info(f"📤 Uploading source video to fal.ai...")
    url = fal_client.upload_file(video_path)
    log.info(f"✅ fal.ai URL: {url}")
    return url

def generate_video(source_url, output_name):
    """Generate วิดีโอใหม่ด้วย fal.ai Kling model"""
    log.info(f"🎬 Generating video: {output_name}")

    result = fal_client.subscribe(
        "fal-ai/kling-video/v1.6/standard/video-to-video",
        arguments={
            "video_url": source_url,
            "prompt": PROMPT_TEMPLATE,
            "duration": "5",
            "aspect_ratio": "9:16",   # vertical สำหรับ TikTok
            "cfg_scale": 0.5
        },
        with_logs=True,
        on_queue_update=lambda update: log.info(f"  ⏳ Status: {update.status if hasattr(update, 'status') else update}")
    )

    video_url = result["video"]["url"]
    log.info(f"✅ Generated! URL: {video_url}")
    return video_url

def download_generated_video(video_url, output_path):
    """Download วิดีโอที่ generate แล้ว"""
    log.info(f"⬇️  Downloading generated video...")
    response = requests.get(video_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    log.info(f"✅ Saved: {output_path}")

# ==================== MAIN ====================
def main():
    log.info("=" * 50)
    log.info(f"🚀 Video Generator เริ่มทำงาน: {datetime.now()}")
    log.info("=" * 50)

    # Setup fal.ai key
    os.environ["FAL_KEY"] = FAL_KEY

    # Connect Google Drive
    service = get_drive_service()

    # สแกนหาวิดีโอต้นฉบับ
    source_videos = list_videos_in_folder(service, SOURCE_FOLDER_ID)

    if not source_videos:
        log.warning("⚠️  ไม่พบวิดีโอใน source folder")
        return

    success_count = 0
    fail_count = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        for video in source_videos:
            video_name = video["name"]
            video_id = video["id"]
            log.info(f"\n{'─'*40}")
            log.info(f"🎥 Processing: {video_name}")

            try:
                # 1. Download source video
                source_path = download_video(service, video_id, video_name, tmp_dir)

                # 2. Upload to fal.ai
                fal_url = upload_video_to_fal(source_path)

                # 3. Generate new video
                output_name = f"generated_{Path(video_name).stem}_{datetime.now().strftime('%Y%m%d')}.mp4"
                generated_url = generate_video(fal_url, output_name)

                # 4. Download generated video
                output_path = os.path.join(tmp_dir, output_name)
                download_generated_video(generated_url, output_path)

                # 5. Upload to Google Drive output folder
                upload_video(service, output_path, OUTPUT_FOLDER_ID, output_name)

                success_count += 1
                log.info(f"✅ สำเร็จ: {video_name} → {output_name}")

            except Exception as e:
                fail_count += 1
                log.error(f"❌ Error processing {video_name}: {str(e)}")
                continue

    log.info(f"\n{'='*50}")
    log.info(f"🏁 เสร็จสิ้น! สำเร็จ: {success_count} | ล้มเหลว: {fail_count}")
    log.info(f"{'='*50}")

if __name__ == "__main__":
    main()
