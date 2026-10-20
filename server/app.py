"""Local-only downloader. Start with python app.py; ffmpeg must be installed."""
import os
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, jsonify, request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["chrome-extension://*", "http://127.0.0.1:*"]}})
jobs = {}
lock = threading.Lock()
OUTPUT = Path.home() / "Downloads" / "VideoDownloader"
OUTPUT.mkdir(parents=True, exist_ok=True)

def valid_url(value):
    try:
        p = urlparse(value)
        host = (p.hostname or "").lower()
        return p.scheme == "https" and host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
    except (ValueError, TypeError):
        return False

def options():
    return {"quiet": True, "no_warnings": True, "noplaylist": True, "ignoreerrors": False,
            "outtmpl": str(OUTPUT / "%(title).180B [%(id)s].%(ext)s"),
            "restrictfilenames": True, "windowsfilenames": True}

@app.post("/info")
def info():
    url = (request.get_json(silent=True) or {}).get("url", "")
    if not valid_url(url):
        return jsonify(error="Geçerli bir YouTube bağlantısı girin."), 400
    try:
        with yt_dlp.YoutubeDL({**options(), "skip_download": True}) as ydl:
            data = ydl.extract_info(url, download=False)
        formats = [{"id": "mp3-128", "label": "MP3 · 128 kbps", "kind": "mp3"},
                   {"id": "mp3-192", "label": "MP3 · 192 kbps", "kind": "mp3"},
                   {"id": "mp3-320", "label": "MP3 · 320 kbps (kaynak kalitesiyle sınırlı)", "kind": "mp3"},
                   {"id": "m4a", "label": "M4A · en iyi ses", "kind": "m4a"},
                   {"id": "best-mp4", "label": "MP4 · en iyi kalite", "kind": "video"},
                   {"id": "best-mkv", "label": "MKV · en iyi kalite", "kind": "video"},
                   {"id": "best-webm", "label": "WebM · en iyi kalite", "kind": "video"}]
        heights = sorted({f.get("height") for f in data.get("formats", []) if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
        for height in heights:
            for ext in ("mp4", "webm"):
                if any(f.get("height") == height and f.get("ext") == ext and f.get("vcodec") != "none" for f in data["formats"]):
                    formats.append({"id": f"{ext}-{height}", "label": f"{ext.upper()} · {height}p", "kind": "video"})
        return jsonify(title=data.get("title", ""), formats=formats)
    except Exception as exc:
        return jsonify(error=str(exc)), 422

def worker(job_id, url, fmt):
    try:
        opts = options()
        if fmt.startswith("mp3-"):
            bitrate = fmt.split("-")[1]
            opts.update(format="bestaudio/best", postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate}])
        elif fmt == "m4a":
            opts.update(format="bestaudio[ext=m4a]/bestaudio", postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}])
        else:
            if fmt == "best-mp4":
                opts.update(format="bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", merge_output_format="mp4")
            elif fmt == "best-mkv":
                opts.update(format="bv*+ba/b", merge_output_format="mkv")
            elif fmt == "best-webm":
                opts.update(format="bv*[ext=webm]+ba[ext=webm]/b[ext=webm]", merge_output_format="webm")
            else:
                ext, height = fmt.split("-")
                if ext not in ("mp4", "webm") or not height.isdigit():
                    raise ValueError("Geçersiz format")
                opts.update(format=f"bv[ext={ext}][height<={height}]+ba[ext={'m4a' if ext == 'mp4' else 'webm'}]/b[ext={ext}][height<={height}]", merge_output_format=ext)
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=True)
        with lock:
            jobs[job_id] = {"status": "done", "file": data.get("title", "Dosya") if data else "Dosya"}
    except Exception as exc:
        with lock:
            jobs[job_id] = {"status": "error", "error": str(exc)}

@app.post("/download")
def download():
    body = request.get_json(silent=True) or {}
    url, fmt = body.get("url", ""), body.get("format_id", "")
    if not valid_url(url):
        return jsonify(error="Geçersiz bağlantı"), 400
    valid = {"mp3-128", "mp3-192", "mp3-320", "m4a", "best-mp4", "best-mkv", "best-webm"}
    if fmt not in valid:
        parts = fmt.split("-")
        if len(parts) != 2 or parts[0] not in ("mp4", "webm") or not parts[1].isdigit() or int(parts[1]) > 4320:
            return jsonify(error="Geçersiz format"), 400
    job_id = uuid.uuid4().hex
    with lock:
        jobs[job_id] = {"status": "running"}
    threading.Thread(target=worker, args=(job_id, url, fmt), daemon=True).start()
    return jsonify(job_id=job_id)

@app.get("/jobs/<job_id>")
def job(job_id):
    with lock:
        result = jobs.get(job_id)
    return jsonify(result) if result else (jsonify(error="Görev bulunamadı"), 404)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
