from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from starlette.background import BackgroundTask

from urllib.parse import urlparse
import yt_dlp
import tempfile
import shutil
import os
import glob
import mimetypes
import re
import json
import subprocess

app = FastAPI(
    title="TikTok Downloader API",
    description="TikTok Video Downloader - ToolNexus",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# 1. VALIDATE TIKTOK URL
# --------------------------------------------------

def is_valid_tiktok_url(url: str):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        return (host == "tiktok.com" or host.endswith(".tiktok.com"))
    except Exception:
        return False


# --------------------------------------------------
# 2. FFPROBE VERIFICATION & TRANSCODING
# --------------------------------------------------

def get_video_codec(filepath: str):
    """Returns the video codec name (e.g., 'h264', 'hevc') or None."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", filepath,
            ],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(result.stdout or "{}")
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream.get("codec_name")
    except Exception as e:
        print(f"ffprobe error: {e}")
    return None

def transcode_to_h264(input_path: str, output_path: str):
    """Converts any video to universally playable H.264 + AAC MP4."""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path
        ], check=True, timeout=120)
        return True
    except Exception as e:
        print(f"Transcoding failed: {e}")
        return False


# --------------------------------------------------
# 3. YT-DLP CONFIGURATION
# --------------------------------------------------

def get_ydl_options(download=False, output_path=None):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "tiktok": {
                "api_hostname": "api16-normal-c-useast1a.tiktokv.com"
            }
        }
    }

    # STRICT H.264 format selection. Avoids HEVC at all costs.
    h264_format = (
        "bv*[vcodec^=avc1]+ba[acodec^=mp4a]"
        "/b[ext=mp4][vcodec^=avc1]"
        "/bv*[vcodec^=avc1]+ba"
        "/b[ext=mp4]"
    )

    if download:
        options.update({
            "format": h264_format,
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(output_path, "%(id)s.%(ext)s"),
            "continuedl": False,
            "overwrites": True,
        })
    else:
        options.update({
            "skip_download": True,
            "format": h264_format,
        })

    return options


# --------------------------------------------------
# 4. EXTRACT VIDEO INFORMATION
# --------------------------------------------------

def extract_info(url: str):
    with yt_dlp.YoutubeDL(get_ydl_options()) as ydl:
        return ydl.extract_info(url, download=False)


# --------------------------------------------------
# 5. HOME
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "API is running",
        "author": "ToolNexus",
        "version": "2.2.0",
        "endpoints": {
            "info": "/api/info?url=TIKTOK_URL",
            "download": "/api/download-file?url=TIKTOK_URL",
            "health": "/health"
        }
    }


# --------------------------------------------------
# 6. VIDEO INFORMATION API
# --------------------------------------------------

@app.get("/api/info")
def get_info(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    try:
        info = extract_info(url)
        video_url = info.get("url")

        if not video_url:
            formats = info.get("formats", [])
            # Prefer H.264 MP4 formats
            mp4_formats = [
                f for f in formats
                if f.get("url") and f.get("ext") == "mp4" 
                and f.get("vcodec", "").startswith("avc1")
            ]
            if not mp4_formats:
                mp4_formats = [f for f in formats if f.get("url") and f.get("ext") == "mp4"]
            
            if mp4_formats:
                mp4_formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                video_url = mp4_formats[-1]["url"]

        return {
            "status": "success",
            "title": info.get("title"),
            "author": info.get("uploader"),
            "author_id": info.get("uploader_id"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "video_url_no_watermark": video_url,
            "original_url": url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# 7. ACTUAL VIDEO DOWNLOAD API (WITH TRANSCODE FALLBACK)
# --------------------------------------------------

@app.get("/api/download-file")
def download_video(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    temp_dir = tempfile.mkdtemp(prefix="tiktok_")

    try:
        # 1. Download using strict H.264 preference
        options = get_ydl_options(download=True, output_path=temp_dir)
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        # 2. Find downloaded file
        files = [f for f in glob.glob(os.path.join(temp_dir, "*")) if os.path.isfile(f) and not f.endswith(".part")]
        if not files:
            raise Exception("Download completed without producing a file.")

        video_path = max(files, key=os.path.getsize)

        if os.path.getsize(video_path) < 1024:
            raise Exception("Downloaded file is too small/incomplete.")

        # 3. Verify Codec. If it's NOT H.264 (e.g., it fell back to HEVC), transcode it.
        codec = get_video_codec(video_path)
        if codec not in ("h264", "avc1"):
            print(f"Warning: Downloaded codec is {codec}. Transcoding to H.264...")
            transcoded_path = os.path.join(temp_dir, "transcoded.mp4")
            
            if transcode_to_h264(video_path, transcoded_path):
                os.remove(video_path)
                video_path = transcoded_path
            else:
                raise Exception("Video codec is not H.264 and transcoding failed.")

        # 4. Prepare response
        extension = os.path.splitext(video_path)[1].lower() or ".mp4"
        mime_type = "video/mp4" # Force MP4 mime type
        
        title = info.get("title") or "tiktok_video"
        filename = re.sub(r"[^\w\- ]", "", title, flags=re.ASCII).strip()
        filename = re.sub(r"\s+", "_", filename)[:80] or "tiktok_video"
        filename += extension

        return FileResponse(
            path=video_path,
            media_type=mime_type,
            filename=filename,
            background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True),
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# 8. HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "TikTok Downloader", "version": "2.2.0"}
