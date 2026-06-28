# 🎬 AI Video Generator

สร้างวิดีโอผู้หญิงสวยขายสินค้าอัตโนมัติ ทุกวันตี 1 (เวลาไทย)

## Flow การทำงาน

```
Google Drive (source) → fal.ai Kling AI → Google Drive (output)
```

---

## ⚙️ Setup (ทำครั้งเดียว)

### Step 1: Google Drive API

1. ไปที่ https://console.cloud.google.com
2. สร้าง Project ใหม่ (ชื่ออะไรก็ได้)
3. ค้นหา **"Google Drive API"** → Enable
4. ไปที่ **IAM & Admin → Service Accounts** → Create Service Account
5. ตั้งชื่อ เช่น `video-generator`
6. ไปที่ Service Account → **Keys → Add Key → JSON** → Download
7. เปิดไฟล์ JSON → Copy ทั้งหมด (จะใส่ใน GitHub Secrets)

### Step 2: แชร์ Google Drive Folders

1. ไปที่ Google Drive → Source folder (โฟลเดอร์วิดีโอต้นฉบับ)
2. คลิก Share → ใส่ **email ของ Service Account** (ดูได้ในไฟล์ JSON ที่ `client_email`)
3. ทำเหมือนกันกับ Output folder

### Step 3: หา Folder IDs

- เปิด Google Drive folder ใน browser
- URL จะเป็น: `https://drive.google.com/drive/folders/FOLDER_ID_HERE`
- Copy ส่วน `FOLDER_ID_HERE`

### Step 4: GitHub Secrets

ไปที่ GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | ค่า |
|-------------|-----|
| `FAL_KEY` | fal.ai API key ของคุณ |
| `GDRIVE_SOURCE_FOLDER_ID` | Folder ID ต้นฉบับ |
| `GDRIVE_OUTPUT_FOLDER_ID` | Folder ID output |
| `GDRIVE_CREDENTIALS_JSON` | ไฟล์ JSON ทั้งหมดของ Service Account |

### Step 5: Push to GitHub

```bash
git init
git add .
git commit -m "Initial setup"
git remote add origin https://github.com/YOUR_USERNAME/video-generator.git
git push -u origin main
```

---

## 🧪 ทดสอบ

ไปที่ GitHub → **Actions → Daily Video Generator → Run workflow**

---

## ⏰ Schedule

รันอัตโนมัติทุกวัน **ตี 1 เวลาไทย** (18:00 UTC)

---

## 📋 Logs

ดู logs ได้ที่ GitHub → Actions → เลือก run → Artifacts → Download logs
