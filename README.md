# TikTok Video Downloader API - No Watermark

Powerful FastAPI based API to download TikTok videos **without watermark** and without errors.

Created by Muzammil Shah

### Features
- ✅ No Watermark Download
- ✅ FastAPI + yt-dlp (most stable extractor)
- ✅ CORS enabled - use from any frontend
- ✅ Deploy ready for Render / Railway / Vercel
- ✅ Error handling for invalid/private videos

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | API status |
| `GET /health` | Health check |
| `GET /api/info?url=` | Get video info + no watermark URL |
| `GET /api/download?url=` | Same as info, for frontend download |

#### Example Request
```
GET /api/download?url=https://www.tiktok.com/@khaby.lame/video/723...
```

#### Example Response
```json
{
  "status": "success",
  "title": "Video title",
  "author": "khaby.lame",
  "video_url_no_watermark": "https://...",
  "thumbnail": "https://..."
}
```

### Local Setup

```bash
git clone https://github.com/YOUR_USERNAME/tiktok-downloader-api.git
cd tiktok-downloader-api
pip install -r requirements.txt
uvicorn main:app --reload
```

Open: http://localhost:8000/docs - You will see Swagger UI

### Deploy to Render (Free)

1. Push this folder to GitHub
2. Go to https://dashboard.render.com -> New Web Service
3. Connect your repo
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Deploy

### Frontend Usage Example

```javascript
const api = "https://your-render-url.onrender.com/api/download?url=" + encodeURIComponent(tiktokUrl)
const res = await fetch(api)
const data = await res.json()
window.location.href = data.video_url_no_watermark
```

### Important Note
Use this tool only for videos you have rights to download. Respect TikTok's Terms of Service and creators' copyright.

### License
MIT
