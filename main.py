
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

app = FastAPI(
    title="TikTok Downloader API",
    description="TikTok Video Downloader - ToolNexus",
    version="2.0.0"
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
# 2. YT-DLP CONFIGURATION
# --------------------------------------------------

def get_ydl_options(download=False, output_path=None):

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "tiktok": {
                "api_hostname":
                "api16-normal-c-useast1a.tiktokv.com"
            }
        }
    }

    if download:

        options.update({
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(
                output_path,
                "%(id)s.%(ext)s"
            ),
            "noplaylist": True,
            "continuedl": False,
            "overwrites": True,
        })

    else:

        options.update({
            "skip_download": True,
            "format": "best[ext=mp4]/best",
        })

    return options


# --------------------------------------------------
# 3. EXTRACT VIDEO INFORMATION
# --------------------------------------------------

def extract_info(url: str):

    with yt_dlp.YoutubeDL(
        get_ydl_options()
    ) as ydl:

        return ydl.extract_info(
            url,
            download=False
        )


# --------------------------------------------------
# 4. HOME
# --------------------------------------------------

@app.get("/")
def root():

    return {
        "status": "API is running",
        "author": "ToolNexus",
        "version": "2.0.0",
        "endpoints": {
            "info": "/api/info?url=TIKTOK_URL",
            "download": "/api/download-file?url=TIKTOK_URL",
            "health": "/health"
        }
    }


# --------------------------------------------------
# 5. VIDEO INFORMATION API
# --------------------------------------------------

@app.get("/api/info")
def get_info(
    url: str = Query(...)
):

    if not is_valid_tiktok_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid TikTok URL"
        )

    try:

        info = extract_info(url)

        video_url = info.get("url")

        if not video_url:

            formats = info.get("formats", [])

            mp4_formats = [
                f for f in formats
                if f.get("url")
                and f.get("ext") == "mp4"
                and f.get("vcodec") != "none"
            ]

            if mp4_formats:
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

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# 6. ACTUAL VIDEO DOWNLOAD API
# --------------------------------------------------

@app.get("/api/download-file")
def download_video(
    url: str = Query(...)
):

    if not is_valid_tiktok_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid TikTok URL"
        )

    temp_dir = tempfile.mkdtemp(
        prefix="tiktok_"
    )

    try:

        options = get_ydl_options(
            download=True,
            output_path=temp_dir
        )

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

        # Find the actual downloaded video file
        files = glob.glob(
            os.path.join(temp_dir, "*")
        )

        video_files = [
            f for f in files
            if os.path.isfile(f)
            and not f.endswith(".part")
        ]

        if not video_files:

            raise Exception(
                "Video download completed without producing a file."
            )

        # Select the downloaded video
        video_path = max(
            video_files,
            key=os.path.getsize
        )

        if os.path.getsize(video_path) < 1024:

            raise Exception(
                "Downloaded video file is incomplete."
            )

        extension = os.path.splitext(
            video_path
        )[1].lower()

        if not extension:
            extension = ".mp4"

        mime_type = (
            mimetypes.guess_type(video_path)[0]
            or "application/octet-stream"
        )

        # Create a clean filename
        title = info.get("title") or "tiktok_video"

        filename = re.sub(
            r'[^\w\- ]',
            '',
            title
        ).strip()

        filename = re.sub(
            r'\s+',
            '_',
            filename
        )[:80]

        if not filename:
            filename = "tiktok_video"

        filename += extension

        return FileResponse(
            path=video_path,
            media_type=mime_type,
            filename=filename,
            background=BackgroundTask(
                shutil.rmtree,
                temp_dir,
                ignore_errors=True
            )
        )

    except Exception as e:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# --------------------------------------------------
# 7. HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "TikTok Downloader"
    }
