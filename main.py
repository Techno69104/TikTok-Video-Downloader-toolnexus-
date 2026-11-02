import asyncio
import ipaddress
import os
import re
import socket
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

VERSION = "9.0.0"

# Set ALLOWED_ORIGINS on Render to your website, e.g. "https://yoursite.com"
# (comma-separated for several). "*" lets anyone call your API.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
CACHE_TTL = 600   # seconds
CACHE_MAX = 200   # entries (keeps memory bounded)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

http_client: httpx.AsyncClient | None = None
download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": UA},
        timeout=httpx.Timeout(15.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
    )
    yield
    await http_client.aclose()


app = FastAPI(title="TikTok Downloader API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- helpers
def is_valid_tiktok_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        return host == "tiktok.com" or host.endswith(".tiktok.com")
    except Exception:
        return False


def cache_get(key: str):
    item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > CACHE_TTL:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def cache_set(key: str, value: dict):
    _cache[key] = (time.time(), value)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


def build_result(title, author, thumbnail, download_url, original_url, source):
    return {
        "status": "success",
        "title": title or "TikTok Video",
        "author": author or "user",
        "thumbnail": thumbnail or "",
        "download_url": download_url,
        # kept so the old README / frontend code keeps working
        "video_url_no_watermark": download_url,
        "original_url": original_url,
        "source": source,
    }


# -------------------------------------------------------------- providers
async def fetch_from_tikwm(client: httpx.AsyncClient, url: str, errors: list):
    """Provider 1: tikwm.com (free tier is rate limited to ~1 req/sec)."""
    for attempt in range(2):
        try:
            resp = await client.get(
                "https://www.tikwm.com/api/", params={"url": url, "hd": 1}
            )
            try:
                data = resp.json()
            except Exception:
                errors.append(f"tikwm: HTTP {resp.status_code}, reply was not JSON (likely blocked)")
                break
            if data.get("code") == 0 and data.get("data"):
                d = data["data"]
                play = d.get("hdplay") or d.get("play")
                if play:
                    if play.startswith("/"):
                        play = "https://www.tikwm.com" + play
                    author = (d.get("author") or {}).get("unique_id")
                    return build_result(
                        d.get("title"), author, d.get("cover"), play, url, "tikwm"
                    )
            msg = str(data.get("msg", "")) or "no video in reply"
            if "limit" in msg.lower() and attempt == 0:
                await asyncio.sleep(1.5)
                continue
            errors.append(f"tikwm: {msg}")
            break
        except Exception as e:
            errors.append(f"tikwm: {type(e).__name__}: {e}")
            break
    return None


async def fetch_from_tiklydown(client: httpx.AsyncClient, url: str, errors: list):
    """Provider 2: tiklydown (response shape varies, so parse defensively)."""
    try:
        resp = await client.get(
            "https://api.tiklydown.eu.org/api/download", params={"url": url}
        )
        if resp.status_code >= 400:
            errors.append(f"tiklydown: HTTP {resp.status_code}")
            return None
        data = resp.json()
        video = data.get("video")
        dl = None
        if isinstance(video, dict):
            dl = video.get("noWatermark") or video.get("no_watermark")
        elif isinstance(video, str):
            dl = video
        if dl:
            author = data.get("author")
            if isinstance(author, dict):
                author = author.get("unique_id") or author.get("name")
            thumb = data.get("thumbnail") or (
                video.get("cover") if isinstance(video, dict) else ""
            )
            return build_result(data.get("title"), author, thumb, dl, url, "tiklydown")
        errors.append("tiklydown: no video link in reply")
    except Exception as e:
        errors.append(f"tiklydown: {type(e).__name__}: {e}")
    return None


PROVIDERS = [fetch_from_tikwm, fetch_from_tiklydown]


async def extract(url: str) -> dict:
    cached = cache_get(url)
    if cached:
        return cached
    errors: list = []
    for provider in PROVIDERS:
        result = await provider(http_client, url, errors)
        if result:
            cache_set(url, result)
            return result
    print("Extraction failed:", errors)
    raise HTTPException(
        status_code=502,
        detail="All extraction services failed. Details: " + " | ".join(errors),
    )


# -------------------------------------------------------------- endpoints
@app.get("/")
async def root():
    return {"status": "ok", "service": "TikTok Downloader API", "version": VERSION}


@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION}


@app.get("/api/info")
@app.get("/api/download")
async def get_info(request: Request, url: str = Query(...)):
    url = url.strip()
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")

    result = dict(await extract(url))
    base = str(request.base_url).rstrip("/")
    result["proxy_url"] = (
        f"{base}/api/file?url={quote(result['download_url'], safe='')}"
        f"&filename=tiktok-video"
    )
    return result


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


@app.get("/api/file")
async def proxy_file(url: str = Query(...), filename: str = Query("tiktok-video")):
    """Streams the video through your server so the browser downloads it as a
    file (instead of just opening it). Streams in 64 KB chunks, so memory stays flat."""
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)[:60] or "tiktok-video"

    if download_sem.locked():
        raise HTTPException(status_code=429, detail="Server busy, try again in a moment.")
    await download_sem.acquire()

    client = httpx.AsyncClient(
        follow_redirects=False,
        headers={"User-Agent": UA, "Referer": "https://www.tiktok.com/"},
        timeout=httpx.Timeout(15.0, read=60.0),
    )
    upstream = None
    try:
        current = url
        for _ in range(4):  # follow a few redirects manually, re-checking each host
            p = urlparse(current)
            if p.scheme not in ("http", "https") or not p.hostname:
                raise HTTPException(status_code=400, detail="Invalid file URL")
            if not await asyncio.to_thread(_is_public_host, p.hostname):
                raise HTTPException(status_code=400, detail="Blocked host")
            upstream = await client.send(client.build_request("GET", current), stream=True)
            if upstream.status_code in (301, 302, 303, 307, 308) and upstream.headers.get("location"):
                current = urljoin(current, upstream.headers["location"])
                await upstream.aclose()
                upstream = None
                continue
            break
        if upstream is None or upstream.status_code >= 400:
            raise HTTPException(status_code=502, detail="Could not fetch the video file")
    except HTTPException:
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()
        download_sem.release()
        raise
    except Exception as e:
        print(f"Proxy failed: {e!r}")
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()
        download_sem.release()
        raise HTTPException(status_code=502, detail="Could not fetch the video file")

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(65536):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            download_sem.release()

    headers = {"Content-Disposition": f'attachment; filename="{safe_name}.mp4"'}
    if upstream.headers.get("content-length"):
        headers["Content-Length"] = upstream.headers["content-length"]
    return StreamingResponse(body(), media_type="video/mp4", headers=headers)
