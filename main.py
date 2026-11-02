from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
import yt_dlp
import httpx

app = FastAPI(title="TikTok Downloader API", version="3.1.0")

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
        # CRITICAL: Force a single file that has BOTH audio and video (progressive MP4).
        # We also prioritize H.264 (avc1) for maximum player compatibility.
        "format": "b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/b"
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
        # 1. Extract the direct CDN URL (takes ~1-2 seconds)
        with yt_dlp.YoutubeDL(get_ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")
        
        # If direct URL is missing, find the highest quality MP4 format
        if not video_url:
            formats = info.get("formats", [])
            mp4_formats = [
                f for f in formats 
                if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec") != "none"
            ]
            if mp4_formats:
                # Sort to find the highest quality
                mp4_formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                video_url = mp4_formats[-1]["url"]

        if not video_url:
            raise Exception("Could not find a valid video URL.")

        # 2. Stream the video directly to the user (0 seconds processing time)
        def stream_video():
            # Using a standard browser user-agent helps prevent TikTok from blocking the CDN request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
            try:
                with httpx.stream("GET", video_url, headers=headers, follow_redirects=True, timeout=30.0) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(chunk_size=16384):
                        yield chunk
            except httpx.HTTPStatusError as e:
                print(f"TikTok CDN Error: {e}")
                # If TikTok blocks the direct stream, this will safely break the loop
                return
            except Exception as e:
                print(f"Streaming Error: {e}")
                return

        return StreamingResponse(
            stream_video(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": 'attachment; filename="tiktok_video.mp4"',
                "Access-Control-Expose-Headers": "Content-Disposition",
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.1.0"}
