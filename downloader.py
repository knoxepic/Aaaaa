import os
import re
import shutil
import tempfile
import threading
import time
import uuid

import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "ytdl-downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

_YT_CLIENTS = ["tv", "web_safari", "android_vr", "android", "mweb"]
_COOKIES_ENV_VARS = ("YOUTUBE_COOKIES", "YTDLP_COOKIES")
_cookies_file = None


def set_cookies_text(text):
    """Persist cookies pasted via the web UI (runtime only, survives until restart)."""
    global _cookies_file
    text = (text or "").strip()
    if not text:
        _cookies_file = ""
        return None
    path = os.path.join(DOWNLOAD_DIR, "runtime-cookiefile.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("\\n", "\n") if "\\n" in text and "\n" not in text else text)
    _cookies_file = path
    return path

_FILE_TTL_SECONDS = 3600


def _cleanup_loop():
    while True:
        try:
            now = time.time()
            for name in os.listdir(DOWNLOAD_DIR):
                p = os.path.join(DOWNLOAD_DIR, name)
                try:
                    if os.path.isfile(p) and now - os.path.getmtime(p) > _FILE_TTL_SECONDS:
                        os.remove(p)
                except OSError:
                    pass
        except OSError:
            pass
        time.sleep(600)


threading.Thread(target=_cleanup_loop, daemon=True).start()

_FMT_LABELS = {
    "144": "144p", "240": "240p", "360": "360p", "480": "480p",
    "576": "576p", "720": "720p HD", "1080": "1080p FHD",
    "1440": "1440p QHD", "2160": "2160p 4K", "4320": "4320p 8K",
}

FfmpegPostProcessor = None
try:
    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
    FfmpegPostProcessor = FFmpegPostProcessor
except Exception:
    pass


def _ffmpeg_location():
    local = os.path.join(BASE_DIR, "ffmpeg")
    if os.path.isfile(local):
        return local
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _cookies_path():
    global _cookies_file
    if _cookies_file is not None:
        return _cookies_file if _cookies_file != "" else None
    existing = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.isfile(existing):
        _cookies_file = existing
        return existing
    for env in _COOKIES_ENV_VARS:
        raw = os.environ.get(env, "").strip()
        if not raw:
            continue
        if os.path.isfile(raw):
            _cookies_file = raw
            return raw
        if raw.startswith("# Netscape") or ".youtube.com" in raw:
            path = os.path.join(DOWNLOAD_DIR, "cookies.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(raw.replace("\\n", "\n") if "\\n" in raw and "\n" not in raw else raw)
            _cookies_file = path
            return path
        _cookies_file = raw
        return raw
    _cookies_file = ""
    return None


def _base_opts(extra=None, clients=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "socket_timeout": 20,
        "retries": 3,
        "restrictfilenames": True,
        "ffmpeg_location": _ffmpeg_location(),
        "extractor_args": {"youtube": {"player_client": clients or _YT_CLIENTS}},
    }
    cookies = _cookies_path()
    if cookies:
        opts["cookiefile"] = cookies
    if extra:
        opts.update(extra)
    return opts


def _safe_title(info):
    title = info.get("title") or "video"
    title = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "_", title).strip()[:120]
    return title or "video"


def _bytes(size):
    if size is None:
        return None
    try:
        return int(size)
    except (TypeError, ValueError):
        return None


def _video_entry(f):
    height = f.get("height") or 0
    label = _FMT_LABELS.get(str(height), f"{height}p" if height else "video")
    fps = f.get("fps")
    dynamic = f.get("dynamic_range") == "HDR"
    return {
        "kind": "video",
        "format_id": f["format_id"],
        "label": label,
        "height": height,
        "fps": int(fps) if fps else None,
        "ext": f.get("ext"),
        "vcodec": f.get("vcodec"),
        "acodec": f.get("acodec"),
        "filesize": _bytes(f.get("filesize") or f.get("filesize_approx")),
        "tbr": f.get("tbr"),
        "hdr": dynamic,
        "progressive": bool(f.get("acodec") not in (None, "none")),
    }


def _audio_entry(f):
    abr = f.get("abr") or 0
    return {
        "kind": "audio",
        "format_id": f["format_id"],
        "label": f"{int(abr)} kbps" if abr else "audio",
        "abr": round(abr, 1) if abr else None,
        "ext": f.get("ext"),
        "acodec": f.get("acodec"),
        "filesize": _bytes(f.get("filesize") or f.get("filesize_approx")),
    }


def _extract(url, extra=None, download=False):
    """Try the configured clients, then fall back to yt-dlp defaults."""
    base = dict(extra or {})
    last_err = None
    for clients in (_YT_CLIENTS, ["default"]):
        try:
            with yt_dlp.YoutubeDL(_base_opts(base, clients=clients)) as ydl:
                return ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as exc:
            last_err = exc
            continue
    raise last_err


def fetch_info(url):
    info = _extract(url)

    videos, audios = [], []
    for f in info.get("formats", []):
        if f.get("format_id") is None:
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        has_video = vcodec and vcodec != "none"
        has_audio = acodec and acodec != "none"
        if has_video:
            videos.append(_video_entry(f))
        elif has_audio:
            audios.append(_audio_entry(f))

    videos.sort(key=lambda x: (x["height"], x.get("fps") or 0), reverse=True)
    audios.sort(key=lambda x: x.get("abr") or 0, reverse=True)

    best_height = max((v["height"] for v in videos), default=0)
    seen = set()
    qualities = []
    for v in videos:
        if v["height"] in seen:
            continue
        seen.add(v["height"])
        qualities.append({
            "label": v["label"] + (" ✨best" if v["height"] == best_height and best_height else ""),
            "height": v["height"],
        })

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url") or url,
        "thumbnail": info.get("thumbnail"),
        "description": info.get("description"),
        "qualities": qualities,
        "formats": {"video": videos, "audio": audios},
        "best": {
            "video": videos[0] if videos else None,
            "audio": audios[0] if audios else None,
        },
    }


def resolve_download(url, format_spec=None, audio_mode=False, audio_format="mp3"):
    """Download to the temp dir and return (path, filename, mimetype)."""
    task_id = uuid.uuid4().hex
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{task_id}.%(ext)s")

    if audio_mode:
        fmt = audio_format if audio_format in ("mp3", "m4a", "opus", "wav", "flac") else "mp3"
        opts = _base_opts({
            "format": format_spec or "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": "0" if fmt == "flac" else "192",
            }],
        })
        ext = fmt
    else:
        opts = _base_opts({
            "format": format_spec or "bestvideo+bestaudio/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
        })
        ext = "mp4"

    info = _extract(url, opts, download=True)
    if "entries" in info:
        info = info["entries"][0]

    filename = f"{_safe_title(info)}.{ext}"
    path = os.path.join(DOWNLOAD_DIR, f"{task_id}.{ext}")
    if not os.path.isfile(path):
        candidates = [p for p in os.listdir(DOWNLOAD_DIR) if p.startswith(task_id)]
        if not candidates:
            raise RuntimeError("Download failed: output file not found")
        path = os.path.join(DOWNLOAD_DIR, candidates[0])
        ext = candidates[0].rsplit(".", 1)[-1]
        filename = f"{_safe_title(info)}.{ext}"

    mimetype = {
        "mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska",
        "mp3": "audio/mpeg", "m4a": "audio/mp4", "opus": "audio/opus",
        "wav": "audio/wav", "flac": "audio/flac",
    }.get(ext, "application/octet-stream")

    return path, filename, mimetype
