from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import httpx

app = FastAPI(title="TikTok Downloader API", version="7.0.0")

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

    try:
        # Directly call the free TikWM API
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get("https://www.tikwm.com/api/", params={"url": url})
            resp.raise_for_status()
            data = resp.json()

        # TikWM returns code=0 for success
        if data.get("code") == 0 and data.get("data"):
            video_data = data["data"]
            play_url = video_data.get("play")
            
            if not play_url:
                raise Exception("TikWM returned no play URL")

            # Ensure the returned URL is complete (TikWM sometimes returns relative paths)
            if play_url.startswith("/"):
                play_url = "https://www.tikwm.com" + play_url

            return {
                "status": "success",
                "title": video_data.get("title", "TikTok Video"),
                "author": video_data.get("author", {}).get("unique_id", "user"),
                "thumbnail": video_data.get("cover", ""),
                "download_url": play_url,
                "original_url": url
            }
        else:
            raise Exception(data.get("msg", "TikWM could not parse this video"))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "version": "7.0.0"}
