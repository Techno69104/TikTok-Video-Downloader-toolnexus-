
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import yt_dlp
import re

app = FastAPI(
    title="TikTok Downloader API",
    description="Powerful API to download TikTok videos without watermark",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def is_valid_tiktok_url(url: str):
    pattern = r"(https?://)?(www\.)?(vm\.)?(vt\.)?tiktok\.com/.*"
    return re.match(pattern, url) is not None

@app.get("/")
def root():
    return {
        "status": "API is running",
        "author": "Muzammil",
        "endpoints": {
            "download": "/api/download?url=TIKTOK_URL",
            "info": "/api/info?url=TIKTOK_URL"
        }
    }

def extract_info(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'format': 'best',
        'extractor_args': {'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info

@app.get("/api/info")
def get_info(url: str = Query(..., description="TikTok Video URL")):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")
    try:
        info = extract_info(url)
        # Get best no-watermark url
        video_url = info.get('url')
        # yt-dlp already returns no-watermark version for tiktok
        if not video_url:
            # fallback to formats
            formats = info.get('formats', [])
            if formats:
                video_url = formats[-1].get('url')

        return {
            "status": "success",
            "title": info.get('title'),
            "author": info.get('uploader'),
            "author_id": info.get('uploader_id'),
            "duration": info.get('duration'),
            "thumbnail": info.get('thumbnail'),
            "video_url_no_watermark": video_url,
            "original_url": url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download")
def download_video(url: str = Query(..., description="TikTok Video URL")):
    # Same as info but designed for frontend to directly download
    result = get_info(url)
    return JSONResponse(content=result)

@app.get("/health")
def health():
    return {"status": "ok"}
