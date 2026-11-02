from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from urllib.parse import urlparse, quote
import yt_dlp
import tempfile
import shutil
import os
import glob
import re
import json
import subprocess

app = FastAPI(
    title="TikTok Downloader API",
    description="TikTok Video Downloader - ToolNexus",
    version="2.3.0"
)

# CRITICAL: expose headers so the frontend can read the filename
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

def get_video_codec(filepath: str):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", filepath],
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
    try:
        # Use ultrafast preset to prevent the request from timing out on Render
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path
        ], check=True, timeout=120)
        return True
    except Exception as e:
        print(f"Transcoding failed: {e}")
        return False

def get_ydl_options(download=False, output_path=None):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "tiktok": {"api_hostname": "api16-normal-c-useast1a.tiktokv.com"}
        }
    }

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
        options.update({"skip_download": True, "format": h264_format})

    return options

@app.get("/")
def root():
    return {"status": "API is running", "version": "2.3.0"}

@app.get("/api/info")
def get_info(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    try:
        with yt_dlp.YoutubeDL(get_ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")
        if not video_url:
            formats = info.get("formats", [])
            mp4_formats = [f for f in formats if f.get("url") and f.get("ext") == "mp4" and f.get("vcodec", "").startswith("avc1")]
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

@app.get("/api/download-file")
def download_video(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    temp_dir = tempfile.mkdtemp(prefix="tiktok_")

    try:
        options = get_ydl_options(download=True, output_path=temp_dir)
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        files = [f for f in glob.glob(os.path.join(temp_dir, "*")) if os.path.isfile(f) and not f.endswith(".part")]
        if not files:
            raise Exception("Download completed without producing a file.")

        video_path = max(files, key=os.path.getsize)

        if os.path.getsize(video_path) < 1024:
            raise Exception("Downloaded file is incomplete.")

        codec = get_video_codec(video_path)
        if codec not in ("h264", "avc1"):
            transcoded_path = os.path.join(temp_dir, "transcoded.mp4")
            if transcode_to_h264(video_path, transcoded_path):
                os.remove(video_path)
                video_path = transcoded_path
            else:
                raise Exception("Video codec is not H.264 and transcoding failed.")

        title = info.get("title") or "tiktok_video"
        filename = re.sub(r"[^\w\- ]", "", title, flags=re.ASCII).strip()
        filename = re.sub(r"\s+", "_", filename)[:80] or "tiktok_video"
        filename += ".mp4"

        # Safely encode filename for the header
        safe_filename = quote(filename)

        # Return FileResponse with explicit download headers
        return FileResponse(
            path=video_path,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            },
            background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True),
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
