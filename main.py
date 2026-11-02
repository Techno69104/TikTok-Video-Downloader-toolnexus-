from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
import yt_dlp
import httpx

app = FastAPI(title="TikTok Downloader API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

def is_valid_tiktok_url(url: str):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        return (host == "tiktok.com" or host.endswith(".tiktok.com"))
    except Exception:
        return False

def get_ydl_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "tiktok": {"api_hostname": "api16-normal-c-useast1a.tiktokv.com"}
        },
        # Prefer H.264. If not available, grab the best mp4.
        "format": "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/best"
    }

@app.get("/api/info")
def get_info(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    try:
        with yt_dlp.YoutubeDL(get_ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)
            
        return {
            "status": "success",
            "title": info.get("title"),
            "author": info.get("uploader"),
            "author_id": info.get("uploader_id"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "original_url": url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-file")
def download_video(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    try:
        # 1. Extract the direct CDN URL (takes ~1 second)
        with yt_dlp.YoutubeDL(get_ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")
        
        # If direct URL is missing, find the highest quality MP4 format
        if not video_url:
            formats = info.get("formats", [])
            mp4_formats = [f for f in formats if f.get("url") and f.get("ext") == "mp4"]
            if mp4_formats:
                mp4_formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                video_url = mp4_formats[-1]["url"]

        if not video_url:
            raise Exception("Could not find a valid video URL.")

        # 2. Stream the video directly to the user (0 seconds processing time)
        def stream_video():
            with httpx.stream("GET", video_url, follow_redirects=True, timeout=30.0) as response:
                for chunk in response.iter_bytes(chunk_size=8192):
                    yield chunk

        return StreamingResponse(
            stream_video(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": 'attachment; filename="tiktok_video.mp4"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
