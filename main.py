from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import yt_dlp
import httpx

app = FastAPI(title="TikTok Downloader API", version="4.1.0")

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

    # ---- First attempt: yt-dlp ----
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
        if not video_url:
            formats = [f for f in info.get("formats", []) if f.get("url") and f.get("vcodec") != "none"]
            if formats:
                formats.sort(key=lambda f: (f.get("tbr") or f.get("filesize") or 0))
                video_url = formats[-1]["url"]

        if video_url:
            return {
                "status": "success",
                "title": info.get("title"),
                "author": info.get("uploader"),
                "thumbnail": info.get("thumbnail"),
                "download_url": video_url,
                "original_url": url,
                "source": "yt-dlp"
            }
    except Exception as e:
        print(f"yt-dlp failed, trying fallback: {e}")

    # ---- Fallback: TikWM API ----
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get("https://www.tikwm.com/api/", params={"url": url})
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") == 0 and data.get("data"):
            video_data = data["data"]
            play_url = video_data.get("play")
            if play_url:
                return {
                    "status": "success",
                    "title": video_data.get("title", "TikTok Video"),
                    "author": video_data.get("author", {}).get("unique_id", "user"),
                    "thumbnail": video_data.get("cover", ""),
                    "download_url": play_url,
                    "original_url": url,
                    "source": "tikwm_fallback"
                }
    except Exception as fallback_err:
        print(f"Fallback also failed: {fallback_err}")

    raise HTTPException(status_code=500, detail="Could not extract video link. The video may be private or the service is temporarily blocked.")

@app.get("/health")
def health():
    return {"status": "ok", "version": "4.1.0"}
