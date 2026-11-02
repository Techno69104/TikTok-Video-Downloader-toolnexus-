# TikTok Video Downloader API

Lightweight FastAPI service that returns a no-watermark TikTok video link.
It does **not** download or store videos on the server (low memory, fits Render free tier).

Created by Muzammil Shah

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | API status |
| `GET /health` | Health check |
| `GET /api/info?url=` | Video info + no-watermark link |
| `GET /api/download?url=` | Same as `/api/info` |
| `GET /api/file?url=&filename=` | Streams the video as a file download |

### Example response
```json
{
  "status": "success",
  "title": "Video title",
  "author": "khaby.lame",
  "thumbnail": "https://...",
  "download_url": "https://your-app.onrender.com/api/file?url=...",
  "video_url_no_watermark": "https://...",
  "proxy_url": "https://your-app.onrender.com/api/file?url=...&filename=tiktok-video",
  "source": "tikwm"
}
```

## Deploy to Render (free)

1. Delete `Dockerfile`, `Procfile` and `runtime.txt` from the repo (not needed).
2. Push to GitHub.
3. Render -> New -> Blueprint (uses `render.yaml`), or New Web Service with:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips "*" --limit-concurrency 50`
4. Set env var `ALLOWED_ORIGINS` to your website URL.

## Frontend example

```javascript
const api = "https://your-app.onrender.com/api/info?url=" + encodeURIComponent(tiktokUrl);
const res = await fetch(api);
const data = await res.json();
if (data.status === "success") {
  window.location.href = data.proxy_url;   // forces a file download
}
```

## Notes
- Free Render services sleep after ~15 min idle; the first request can take 30-60 s.
- Extraction uses yt-dlp on your own server (TikWM as fallback). TikTok may block datacenter IPs at times; yt-dlp is unpinned so each redeploy picks up the latest TikTok fixes.
- Only download videos you have rights to. Respect TikTok's Terms and creators' copyright.

MIT License
