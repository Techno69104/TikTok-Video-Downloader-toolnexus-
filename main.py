from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import yt_dlp
import httpx
import re
import os
import base64
import tempfile

app = FastAPI(title="TikTok Downloader API", version="6.0.0")

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

def get_cookies_file():
    """Helper to read TIKTOK_COOKIES_B64 env variable for restricted videos."""
    b64 = os.environ.get("TIKTOK_COOKIES_B64", "")
    if not b64:
        return None
    try:
        text = base64.b64decode(b64).decode()
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(text)
        f.close()
        return f.name
    except Exception:
        return None

# ==========================================
# LAYER 1: yt-dlp with Chrome Impersonation
# ==========================================
def try_ytdlp(url: str):
    opts = {
        "quiet": True, 
        "no_warnings": True, 
        "noplaylist": True,
        "extractor_args": {"tiktok": {"api_hostname": "api16-normal-c-useast1a.tiktokv.com"}},
        "format": "b[ext=mp4]/bv*+ba/b",
        "impersonate": "chrome",
    }
    
    cf = get_cookies_file()
    if cf:
        opts["cookiefile"] = cf

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        video_url = info.get("url")
        if not video_url:
            formats = [f for f in info.get("formats", []) if f.get("url") and f.get("vcodec") != "none"]
            if formats:
                formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                video_url = formats[-1]["url"]

        if video_url:
            return {
                "download_url": video_url, 
                "title": info.get("title"), 
                "author": info.get("uploader"), 
                "thumbnail": info.get("thumbnail")
            }
    except Exception as e:
        print(f"Layer 1 (yt-dlp) failed: {e}")
    return None

# ==========================================
# LAYER 2: TikTok Direct Mobile API
# ==========================================
def try_mobile_api(url: str):
    match = re.search(r'/video/(\d+)', url)
    if not match:
        return None
    video_id = match.group(1)
    
    api_url = "https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/multi/aweme/detail/"
    headers = {
        "User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 12; en; SM-G998B)",
        "Content-Type": "application/json",
        "X-Argus": "",
    }
    
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(api_url, params={"aweme_ids": video_id}, headers=headers)
            data = resp.json()
            details = data.get("aweme_details", [])
            
            if details:
                video = details[0].get("video", {})
                urls = video.get("play_addr", {}).get("url_list", [])
                if urls:
                    return {
                        "download_url": urls[0], 
                        "title": details[0].get("desc", "TikTok Video"), 
                        "author": details[0].get("author", {}).get("unique_id", "user"), 
                        "thumbnail": video.get("cover", {}).get("url_list", [""])[0]
                    }
    except Exception as e:
        print(f"Layer 2 (Mobile API) failed: {e}")
    return None

# ==========================================
# MAIN API ENDPOINT
# ==========================================
@app.get("/api/info")
def get_info(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    # Execute fallback sequence
    for extractor in [try_ytdlp, try_mobile_api]:
        result = extractor(url)
        if result and result.get("download_url"):
            return {
                "status": "success", 
                **result, 
                "original_url": url
            }

    raise HTTPException(
        status_code=500, 
        detail="All extraction methods failed. The video may be private, region-blocked, or TikTok is blocking this server's IP."
    )

@app.get("/health")
def health():
    return {"status": "ok", "version": "6.0.0"}
