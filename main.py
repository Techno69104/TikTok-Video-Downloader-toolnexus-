import asyncio
import os
import re
import shutil
import tempfile
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from urllib.parse import quote, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

VERSION = "11.0.0"

# Set ALLOWED_ORIGINS on Render to your website, e.g. "https://yoursite.com"
# (comma-separated for several). "*" lets anyone call your API.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
CACHE_TTL = 600   # seconds (TikTok stream links expire, so keep this short)
CACHE_MAX = 100   # entries, keeps memory bounded

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

http_client: httpx.AsyncClient | None = None
download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
ytdlp_lock = asyncio.Semaphore(1)  # one yt-dlp extraction at a time (memory)
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


def build_result(title, author, thumbnail, original_url, source, stream):
    """`_stream` is private (never sent to the client): the real video URL plus
    any headers/cookies needed to fetch it."""
    return {
        "status": "success",
        "title": title or "TikTok Video",
        "author": author or "user",
        "thumbnail": thumbnail or "",
        "original_url": original_url,
        "source": source,
        "_stream": stream,
    }


def clean_error(e: Exception) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))  # strip colour codes
    return f"{type(e).__name__}: {msg[:300]}"


# -------------------------------------------------------------- providers
def _ytdlp_extract(url: str) -> dict:
    import yt_dlp  # imported lazily so startup stays light

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

        formats = [
            f for f in (info.get("formats") or [])
            if f.get("url")
            and f.get("vcodec") != "none"
            and (f.get("protocol") or "https").startswith("http")
        ]
        # skip the watermarked "download" format
        no_wm = [
            f for f in formats
            if "watermark" not in (f.get("format_note") or "").lower()
            and f.get("format_id") != "download"
        ]
        pool = no_wm or formats
        if pool:
            best = max(
                pool,
                key=lambda f: (
                    str(f.get("vcodec") or "").startswith("h264"),
                    f.get("height") or 0,
                    f.get("tbr") or 0,
                ),
            )
        else:
            best = info

        stream_url = best.get("url")
        if not stream_url:
            raise RuntimeError("no playable video URL found")

        headers = dict(info.get("http_headers") or {})
        headers.update(best.get("http_headers") or {})
        cookie = best.get("cookies") or info.get("cookies") or ""
        if not cookie:
            try:
                cookie = ydl.cookiejar.get_cookie_header(stream_url) or ""
            except Exception:
                cookie = ""

    return {
        "title": info.get("title") or info.get("description"),
        "author": info.get("uploader") or info.get("channel"),
        "thumbnail": info.get("thumbnail"),
        "stream": {"url": stream_url, "headers": headers, "cookie": cookie},
    }


async def fetch_from_ytdlp(client: httpx.AsyncClient, url: str, errors: list):
    """Provider 1: yt-dlp running on your own server (no third-party API)."""
    try:
        async with ytdlp_lock:
            data = await asyncio.wait_for(
                asyncio.to_thread(_ytdlp_extract, url), timeout=45
            )
        return build_result(
            data["title"], data["author"], data["thumbnail"], url, "yt-dlp", data["stream"]
        )
    except Exception as e:
        errors.append(f"yt-dlp: {clean_error(e)}")
    return None


async def fetch_from_tikwm(client: httpx.AsyncClient, url: str, errors: list):
    """Provider 2 (fallback): tikwm.com. May block datacenter IPs."""
    try:
        resp = await client.get("https://www.tikwm.com/api/", params={"url": url, "hd": 1})
        try:
            data = resp.json()
        except Exception:
            errors.append(f"tikwm: HTTP {resp.status_code}, not JSON (likely blocked)")
            return None
        if data.get("code") == 0 and data.get("data"):
            d = data["data"]
            play = d.get("hdplay") or d.get("play")
            if play:
                if play.startswith("/"):
                    play = "https://www.tikwm.com" + play
                author = (d.get("author") or {}).get("unique_id")
                return build_result(
                    d.get("title"), author, d.get("cover"), url, "tikwm",
                    {"url": play, "headers": {}, "cookie": ""},
                )
        errors.append(f"tikwm: {data.get('msg') or 'no video in reply'}")
    except Exception as e:
        errors.append(f"tikwm: {clean_error(e)}")
    return None



TMP_BASE = os.path.join(tempfile.gettempdir(), "tikdl")
os.makedirs(TMP_BASE, exist_ok=True)


def sweep_tmp():
    """Delete leftover temp download folders older than 10 minutes."""
    now = time.time()
    try:
        for name in os.listdir(TMP_BASE):
            p = os.path.join(TMP_BASE, name)
            if now - os.path.getmtime(p) > 600:
                shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass


def _ytdlp_download(url: str, outdir: str) -> str:
    """Let yt-dlp download the file itself (it handles TikTok's cookies/headers).
    Writes to disk, not RAM, so memory stays low."""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "outtmpl": os.path.join(outdir, "video.%(ext)s"),
        # prefer H.264 without watermark; never pick the watermarked "download" format first
        "format": "best[format_id!=download][vcodec^=h264]/best[format_id!=download]/best",
        "max_filesize": 150 * 1024 * 1024,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [f for f in os.listdir(outdir) if not f.endswith((".part", ".ytdl"))]
    if not files:
        raise RuntimeError("yt-dlp finished but produced no file")
    return os.path.join(outdir, files[0])


PROVIDERS = [fetch_from_ytdlp, fetch_from_tikwm]


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
        detail="All extraction methods failed. Details: " + " | ".join(errors),
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

    result = await extract(url)
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    base = str(request.base_url).rstrip("/")
    proxy = f"{base}/api/file?url={quote(url, safe='')}&filename=tiktok-video"
    public["proxy_url"] = proxy
    # TikTok CDN links need special headers, so the browser must download via our proxy
    public["download_url"] = proxy
    public["video_url_no_watermark"] = proxy
    return public


@app.get("/api/file")
async def proxy_file(url: str = Query(...), filename: str = Query("tiktok-video")):
    """Streams the video to the browser as a file download in 64 KB chunks,
    so memory stays flat. Takes the TikTok page URL, never an arbitrary URL."""
    url = url.strip()
    if not is_valid_tiktok_url(url):
        raise HTTPException(status_code=400, detail="Invalid TikTok URL")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)[:60] or "tiktok-video"

    info = await extract(url)
    stream = info["_stream"]

    if info.get("source") == "yt-dlp":
        sweep_tmp()
        outdir = tempfile.mkdtemp(dir=TMP_BASE)
        try:
            async with ytdlp_lock:
                path = await asyncio.wait_for(
                    asyncio.to_thread(_ytdlp_download, url, outdir), timeout=90
                )
        except Exception as e:
            shutil.rmtree(outdir, ignore_errors=True)
            _cache.pop(url, None)
            detail = clean_error(e)
            print("yt-dlp download failed:", detail)
            raise HTTPException(status_code=502, detail="Download failed: " + detail)
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=f"{safe_name}.mp4",
            background=BackgroundTask(shutil.rmtree, outdir, True),
        )

    if download_sem.locked():
        raise HTTPException(status_code=429, detail="Server busy, try again in a moment.")
    await download_sem.acquire()

    headers = {"User-Agent": UA, "Referer": "https://www.tiktok.com/"}
    for k, v in (stream.get("headers") or {}).items():
        if k.lower() not in ("accept-encoding", "host"):
            headers[k] = v
    if stream.get("cookie"):
        headers["Cookie"] = stream["cookie"]

    client = httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        timeout=httpx.Timeout(15.0, read=60.0),
    )
    try:
        upstream = await client.send(client.build_request("GET", stream["url"]), stream=True)
    except Exception as e:
        await client.aclose()
        download_sem.release()
        _cache.pop(url, None)
        print("Proxy connect failed:", clean_error(e))
        raise HTTPException(status_code=502, detail="Could not fetch the video file")

    if upstream.status_code >= 400:
        code = upstream.status_code
        await upstream.aclose()
        await client.aclose()
        download_sem.release()
        _cache.pop(url, None)  # link probably expired; re-extract next time
        raise HTTPException(status_code=502, detail=f"Video server returned HTTP {code}")

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(65536):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            download_sem.release()

    out_headers = {"Content-Disposition": f'attachment; filename="{safe_name}.mp4"'}
    if upstream.headers.get("content-length"):
        out_headers["Content-Length"] = upstream.headers["content-length"]
    return StreamingResponse(body(), media_type="video/mp4", headers=out_headers)
