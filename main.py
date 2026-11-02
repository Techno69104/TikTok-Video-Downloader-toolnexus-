from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import httpx
import asyncio

app = FastAPI(title="TikTok Downloader API", version="8.0.0")

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

# --- Provider 1: TikWM (Primary) ---
async def fetch_from_tikwm(client: httpx.AsyncClient, url: str):
    try:
        resp = await client.get("https://www.tikwm.com/api/", params={"url": url}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0 and data.get("data"):
            video_data = data["data"]
            play_url = video_data.get("play")
            if play_url:
                if play_url.startswith("/"):
                    play_url = "https://www.tikwm.com" + play_url
                return {
                    "status": "success",
                    "title": video_data.get("title", "TikTok Video"),
                    "author": video_data.get("author", {}).get("unique_id", "user"),
                    "thumbnail": video_data.get("cover", ""),
                    "download_url": play_url,
                    "original_url": url,
                    "source": "tikwm"
                }
    except Exception as e:
        print(f"TikWM failed: {e}")
    return None

# --- Provider 2: TikMate (Backup) ---
async def fetch_from_tikmate(client: httpx.AsyncClient, url: str):
    try:
        # TikMate often requires a POST request
        resp = await client.post("https://tikmate.app/api/download", data={"url": url}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success" and data.get("data"):
            video_url = data["data"].get("video_url")
            if video_url:
                return {
                    "status": "success",
                    "title": data["data"].get("title", "TikTok Video"),
                    "author": data["data"].get("author", "user"),
                    "thumbnail": data["data"].get("cover", ""),
                    "download_url": video_url,
                    "original_url": url,
                    "source": "tikmate"
                }
    except Exception as e:
        print(f"TikMate failed: {e}")
    return None

# --- Provider 3: TiklyDown (Backup) ---
async def fetch_from_tiklydown(client: httpx.AsyncClient, url: str):
    try:
        resp = await client.get(f"https://api.tiklydown.eu.org/api/download?url={url}", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("video"):
            return {
                "status": "success",
                "title": data.get("title", "TikTok Video"),
                "author": data.get("author", {}).get("unique_id", "user"),
                "thumbnail": data.get("thumbnail", ""),
                "download_url": data["video"],
                "original_url": url,
                "source": "tiklydown"
            }
    except Exception as e:
        print(f"TiklyDown failed: {e}")
    return None

@app.get("/api/info")
async def get_info(url: str = Query(...)):
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    # Try providers in order
    providers = [fetch_from_tikwm, fetch_from_tikmate, fetch_from_tiklydown]
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for provider in providers:
            result = await provider(client, url)
            if result:
                return result

    raise HTTPException(
        status_code=500, 
        detail="All free extraction services are currently blocked or unavailable. Please try again later."
    )

@app.get("/health")
async def health():
    return {"status": "ok", "version": "8.0.0"}
