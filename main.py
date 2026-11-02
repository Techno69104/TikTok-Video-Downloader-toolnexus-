from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
import yt_dlp
import httpx

app = FastAPI(title="TikTok Downloader API", version="3.2.0")

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
        # BULLETPROOF FORMAT STRING:
        # 1. Try to find a progressive MP4 (both audio & video, H.264)
        # 2. Try to find any progressive MP4
        # 3. Fall back to whatever best format is available
        "format": "b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/best"
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
        print(f"Info extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-file")
def download_video(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    try:
        # 1. Extract the direct CDN URL
        with yt_dlp.YoutubeDL(get_ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")
        
        # 2. Intelligent Fallback: If direct URL is missing, dig into the formats array
        if not video_url:
            formats = info.get("formats", [])
            
            # Filter out broken formats
            valid_formats = [f for f in formats if f.get("url") and f.get("vcodec") != "none"]
            
            if valid_formats:
                # Try to find a combined MP4 first
                combined_mp4 = [f for f in valid_formats if f.get("ext") == "mp4" and f.get("acodec") != "none"]
                
                if combined_mp4:
                    combined_mp4.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                    video_url = combined_mp4[-1]["url"]
                else:
                    # Fallback to highest quality video stream (might be video-only)
                    valid_formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                    video_url = valid_formats[-1]["url"]

        if not video_url:
            raise Exception("Could not find a downloadable video stream for this link.")

        # 3. Stream the video directly to the user
        def stream_video():
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Referer": "https://www.tiktok.com/"
            }
            try:
                with httpx.stream("GET", video_url, headers=headers, follow_redirects=True, timeout=30.0) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(chunk_size=16384):
                        yield chunk
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
        print(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.2.0"}
