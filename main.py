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
    version="2.1.0"
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

        return (
            host == "tiktok.com"
            or host.endswith(".tiktok.com")
        )

    except Exception:
        return False


# --------------------------------------------------
# 2. FFPROBE VERIFICATION
# --------------------------------------------------

def ffprobe_streams(filepath: str):
    """
    Returns a dict with 'video' and 'audio' codec names (or None).
    Raises if ffprobe is missing or fails.
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            filepath,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])

    video_codec = None
    audio_codec = None
    for s in streams:
        if s.get("codec_type") == "video" and video_codec is None:
            video_codec = s.get("codec_name")
        elif s.get("codec_type") == "audio" and audio_codec is None:
            audio_codec = s.get("codec_name")

    return {"video": video_codec, "audio": audio_codec}


def is_playable_mp4(filepath: str) -> bool:
    """
    Returns True if file contains an H.264 video stream in an MP4 container.
    H.264 (avc1) is the most universally playable codec.
    """
    try:
        info = ffprobe_streams(filepath)
        return info.get("video") in ("h264", "avc1")
    except Exception:
        # If ffprobe is unavailable, don't block the download.
        return True


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

    if download:

        # Prefer H.264 + AAC so the result is playable everywhere.
        # Fall back to any MP4, then best.
        options.update({
            "format": (
                "bv*[vcodec^=avc1]+ba[acodec^=mp4a]"
                "/b[ext=mp4][vcodec^=avc1]"
                "/b[ext=mp4]"
                "/best"
            ),
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(output_path, "%(id)s.%(ext)s"),
            "continuedl": False,
            "overwrites": True,
        })

    else:

        options.update({
            "skip_download": True,
            "format": (
                "bv*[vcodec^=avc1]+ba[acodec^=mp4a]"
                "/b[ext=mp4][vcodec^=avc1]"
                "/b[ext=mp4]"
                "/best"
            ),
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
        "version": "2.1.0",
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
                if f.get("url")
                and f.get("ext") == "mp4"
                and f.get("vcodec") != "none"
                and f.get("vcodec", "").startswith("avc1")
            ]

            if not mp4_formats:
                mp4_formats = [
                    f for f in formats
                    if f.get("url")
                    and f.get("ext") == "mp4"
                    and f.get("vcodec") != "none"
                ]

            if mp4_formats:
                # Pick the highest bitrate H.264 version
                mp4_formats.sort(
                    key=lambda f: (f.get("tbr") or f.get("filesize") or 0)
                )
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
# 7. ACTUAL VIDEO DOWNLOAD API
# --------------------------------------------------

def _download_and_pick(url: str, temp_dir: str):
    """
    Download with preferred H.264 format, verify with ffprobe.
    If the result is not playable MP4, retry with a progressive
    MP4-only format.
    """
    options = get_ydl_options(download=True, output_path=temp_dir)

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [
        f for f in glob.glob(os.path.join(temp_dir, "*"))
        if os.path.isfile(f) and not f.endswith(".part")
    ]
    if not files:
        raise Exception("Download completed without producing a file.")

    video_path = max(files, key=os.path.getsize)

    if os.path.getsize(video_path) < 1024:
        raise Exception("Downloaded file is too small / incomplete.")

    if not is_playable_mp4(video_path):
        # Retry with a strict progressive MP4 (H.264 only, no merge)
        try:
            os.remove(video_path)
        except OSError:
            pass

        fallback = dict(options)
        fallback["format"] = "b[ext=mp4][vcodec^=avc1]/b[ext=mp4]/best"
        fallback.pop("merge_output_format", None)

        with yt_dlp.YoutubeDL(fallback) as ydl:
            ydl.extract_info(url, download=True)

        files = [
            f for f in glob.glob(os.path.join(temp_dir, "*"))
            if os.path.isfile(f) and not f.endswith(".part")
        ]
        if not files:
            raise Exception("Fallback download produced no file.")

        video_path = max(files, key=os.path.getsize)

    return info, video_path


@app.get("/api/download-file")
def download_video(url: str = Query(...)):

    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    temp_dir = tempfile.mkdtemp(prefix="tiktok_")

    try:
        info, video_path = _download_and_pick(url, temp_dir)

        extension = os.path.splitext(video_path)[1].lower() or ".mp4"

        mime_type = (
            mimetypes.guess_type(video_path)[0]
            or "video/mp4"
        )

        title = info.get("title") or "tiktok_video"

        filename = re.sub(r"[^\w\- ]", "", title, flags=re.ASCII).strip()
        filename = re.sub(r"\s+", "_", filename)[:80] or "tiktok_video"
        filename += extension

        return FileResponse(
            path=video_path,
            media_type=mime_type,
            filename=filename,
            background=BackgroundTask(
                shutil.rmtree, temp_dir, ignore_errors=True
            ),
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# 8. HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "TikTok Downloader",
        "version": "2.1.0"
    }
