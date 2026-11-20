# Knox

Web UI + JSON API to fetch YouTube video info and download video in every
available quality (144p → 8K) or extract audio (MP3 / M4A / Opus / WAV / FLAC),
powered by `yt-dlp`.

> **Disclaimer:** for personal, educational use only. Respect YouTube's Terms
> of Service, copyright law, and creators' rights. Download only content you
> own or that is explicitly licensed for download (e.g. Creative Commons).

## Run

```bash
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:8000
```

Production:

```bash
gunicorn -w 2 -t 600 --bind 0.0.0.0:8000 app:app
```

Environment variables:

| Variable              | Default | Meaning                                        |
|-----------------------|---------|------------------------------------------------|
| `PORT`                | `8000`  | Port when run directly                          |
| `MAX_DURATION_SECONDS`| off    | Reject videos longer than N seconds (0 = off)   |

ffmpeg is required for merging video+audio and audio transcoding. In the Docker
image (HF Spaces / Railway) it is pre-installed; locally the app falls back to
system `ffmpeg` or the `imageio-ffmpeg` Python package.

## REST API

### `GET /api/info?url=<youtube url>`

Returns metadata, the deduplicated list of available qualities, and every format.

```json
{
  "ok": true,
  "info": {
    "title": "...", "uploader": "...", "duration_string": "3:21",
    "thumbnail": "https://...",
    "qualities": [{"label": "1080p FHD ✨best", "height": 1080}, ...],
    "formats": {
      "video":  [{"format_id": "137", "label": "1080p FHD", "fps": 30, "ext": "mp4",
                  "filesize": 12345678, "progressive": false, "hdr": false, ...}, ...],
      "audio":  [{"format_id": "140", "label": "128 kbps", "ext": "m4a", "filesize": 3210000}, ...],
    },
    "best": {"video": {...}, "audio": {...}}
  }
}
```

### `GET /api/formats?url=<url>`

Same format listing without the full metadata payload.

### `GET /api/download?url=<url>&...`

Streams the file as an attachment. Mutually combinable options:

| Parameter      | Values / example                            | Effect                                   |
|----------------|---------------------------------------------|------------------------------------------|
| `fid`          | `137` (a `format_id` from `/api/info`)      | Download that exact format               |
| `quality`      | `2160`,`1440`,`1080`,`720`,`480`,`360`,`240`,`144` | Best video at ≤ height, merged to MP4 |
| `mode`         | `audio`                                     | Best audio only                          |
| `audio_format` | `mp3` (default), `m4a`, `opus`, `wav`, `flac` | Transcode audio (requires ffmpeg)      |
| `format`       | `best` (default)                            | `best` = bestvideo+bestaudio merged MP4  |

Examples:

```bash
# Web UI page
curl http://127.0.0.1:8000/

# Info
curl "http://127.0.0.1:8000/api/info?url=https://youtu.be/<id>"

# Best quality MP4
curl -LOJ "http://127.0.0.1:8000/api/download?url=https://youtu.be/<id>"

# 720p
curl -LOJ "http://127.0.0.1:8000/api/download?url=https://youtu.be/<id>&quality=720"

# Exact format id from /api/info
curl -LOJ "http://127.0.0.1:8000/api/download?url=https://youtu.be/<id>&fid=137"

# MP3 audio
curl -LOJ "http://127.0.0.1:8000/api/download?url=https://youtu.be/<id>&mode=audio&audio_format=mp3"
```

Other endpoints: `GET /api/health`.

Files are written to a temp dir and auto-deleted after ~1 hour by a background
cleanup thread.

## Project layout

```
app.py           Flask app: routes, param parsing, file streaming
downloader.py    yt-dlp logic: info extraction + download/merge/transcode
templates/       Web UI
static/          CSS + frontend JS
ffmpeg           Bundled static ffmpeg (auto-detected)
```

## Fixing "Failed to extract any player response" (cloud/datacenter IPs)

YouTube bot-checks datacenter IPs (HF Spaces, Render, Railway). If extraction
fails like this, provide YouTube cookies:

1. Install the browser extension **"Get cookies.txt LOCALLY"** (Chrome/Firefox)
2. Open **youtube.com** while logged in and export cookies in **Netscape format**
   (use a throwaway Google account if possible)
3. On Hugging Face Spaces: Space Settings -> Variables and secrets -> New secret
   - Name: `YOUTUBE_COOKIES`
   - Value: paste the full cookies.txt content
4. Restart the Space. The app also auto-detects a `cookies.txt` file placed
   next to `app.py`, or a file path in the same env var.

The app now also retries with yt-dlp default clients (incl. `tv`) before
giving up, which already resolves most datacenter-IP extraction failures.
