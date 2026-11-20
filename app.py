import os

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS

import downloader

app = Flask(__name__)
CORS(app)

MAX_DURATION_SECONDS = int(os.environ.get("MAX_DURATION_SECONDS", 0)) or None


def _client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def _error(message, status=400):
    return jsonify({"ok": False, "error": message, "status": status}), status


_HINT = (" | Hint: YouTube bot-checked this server IP. Add the YOUTUBE_COOKIES "
         "Space secret with youtube.com cookies in Netscape format (see README), "
         "then restart the app.")


def _yt_error(exc):
    msg = str(exc)
    if ("player response" in msg or "page needs to be reloaded" in msg
            or "Sign in to confirm" in msg or "CookieLoadError" in msg):
        msg += _HINT
        return _error(msg, 502)
    return _error(msg, 502)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "version": "1.0.0"})


@app.get("/api/info")
def api_info():
    url = (request.args.get("url") or "").strip()
    if not url:
        return _error("Missing 'url' query parameter.")
    try:
        info = downloader.fetch_info(url)
    except downloader.yt_dlp.utils.DownloadError as exc:
        return _yt_error(exc)
    except Exception as exc:
        return _error(f"Unexpected error: {exc}", 500)
    if MAX_DURATION_SECONDS and info.get("duration") and info["duration"] > MAX_DURATION_SECONDS:
        return _error(f"Video longer than {MAX_DURATION_SECONDS}s is not allowed.", 413)
    return jsonify({"ok": True, "info": info})


@app.get("/api/formats")
def api_formats():
    url = (request.args.get("url") or "").strip()
    if not url:
        return _error("Missing 'url' query parameter.")
    try:
        info = downloader.fetch_info(url)
    except downloader.yt_dlp.utils.DownloadError as exc:
        return _yt_error(exc)
    except Exception as exc:
        return _error(f"Unexpected error: {exc}", 500)
    return jsonify({
        "ok": True,
        "title": info["title"],
        "formats": info["formats"],
        "qualities": info["qualities"],
        "best": info["best"],
    })


def _parse_common():
    url = (request.args.get("url") or "").strip()
    if not url:
        return None, _error("Missing 'url' query parameter.")
    return url, None


@app.get("/api/download")
def api_download():
    url, err = _parse_common()
    if err:
        return err

    fmt_choice = (request.args.get("format") or "best").strip().lower()
    quality = (request.args.get("quality") or "").strip().lower()
    mode = (request.args.get("mode") or "").strip().lower()      # video | audio
    audio_format = (request.args.get("audio_format") or "mp3").strip().lower()
    format_id = (request.args.get("fid") or request.args.get("format_id") or "").strip()

    format_spec = None
    audio_mode = False

    if format_id:
        format_spec = format_id
        if mode == "audio":
            audio_mode = True
    elif mode == "audio":
        audio_mode = True
        format_spec = "bestaudio/best"
    elif fmt_choice in ("audio", "mp3", "m4a", "opus"):
        audio_mode = True
        if fmt_choice in ("m4a", "opus"):
            audio_format = fmt_choice
    elif fmt_choice in ("best", "bestvideo", "hd"):
        format_spec = "bestvideo+bestaudio/best"
    elif quality:
        match = [q for q in ("2160", "1440", "1080", "720", "480", "360", "240", "144") if quality.startswith(q)]
        if match:
            h = match[0]
            format_spec = (
                f"bestvideo[height<={h}]+bestaudio/"
                f"best[height<={h}]/bestvideo+bestaudio/best"
            )
        else:
            format_spec = "bestvideo+bestaudio/best"
    else:
        format_spec = "bestvideo+bestaudio/best"

    try:
        path, filename, mimetype = downloader.resolve_download(
            url, format_spec=format_spec, audio_mode=audio_mode, audio_format=audio_format
        )
    except downloader.yt_dlp.utils.DownloadError as exc:
        return _yt_error(exc)
    except Exception as exc:
        return _error(f"Unexpected error: {exc}", 500)

    try:
        return send_file(
            path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename,
            conditional=True,
        )
    except Exception as exc:
        return _error(f"Failed to stream file: {exc}", 500)


@app.post("/api/cookies")
def api_cookies():
    key_required = os.environ.get("COOKIE_KEY", "").strip()
    if not key_required:
        return _error("Cookie saving is disabled. Set the COOKIE_KEY secret/env var first.", 403)
    data = request.get_json(silent=True) or {}
    if data.get("key", "") != key_required:
        return _error("Wrong key.", 403)
    cookies = (data.get("cookies") or "").strip()
    if not cookies:
        return _error("Cookies text is empty.", 400)
    if "youtube.com" not in cookies:
        return _error("This does not look like a youtube.com cookies file (missing 'youtube.com').", 400)
    path = downloader.set_cookies_text(cookies)
    return jsonify({"ok": True, "saved": path})


@app.errorhandler(404)
def not_found(_):
    return _error("Not found. See GET /api/health, /api/info?url=..., /api/formats, /api/download", 404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="127.0.0.1", port=port, threaded=True)
