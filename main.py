from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import yt_dlp

app = FastAPI(title="TikTok Downloader API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
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

@app.get("/api/info")
def get_info(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {"tiktok": {"api_hostname": "api16-normal-c-useast1a.tiktokv.com"}},
        "format": "b[ext=mp4]/bv*+ba/b" 
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")
        
        # If combined URL is not found, find the best video format
        if not video_url:
            formats = [f for f in info.get("formats", []) if f.get("url") and f.get("vcodec") != "none"]
            if formats:
                formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                video_url = formats[-1]["url"]

        if not video_url:
            raise Exception("Could not extract direct video link.")

        return {
            "status": "success",
            "title": info.get("title"),
            "author": info.get("uploader"),
            "thumbnail": info.get("thumbnail"),
            "download_url": video_url,
            "original_url": url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "version": "4.0.0"}
