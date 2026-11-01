"""Local-only downloader. Start with python app.py; ffmpeg must be installed."""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from flask import Flask, jsonify, request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["chrome-extension://*", "http://127.0.0.1:*"]}})
jobs = {}
cancel_events = {}
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

@app.post("/playlist")
def playlist():
    url = (request.get_json(silent=True) or {}).get("url", "")
    if not valid_url(url) or not parse_qs(urlparse(url).query).get("list"):
        return jsonify(error="Geçerli oynatma listesi bağlantısı girin."), 400
    try:
        opts = {**options(), "noplaylist": False, "extract_flat": "in_playlist", "playlistend": 300}
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
        entries = []
        for item in (data or {}).get("entries", []):
            if item and item.get("id") and len(item["id"]) == 11:
                entries.append({"id": item["id"], "title": item.get("title") or "Video",
                                "url": "https://www.youtube.com/watch?v=" + item["id"]})
        return jsonify(title=(data or {}).get("title") or "Oynatma listesi", items=entries)
    except Exception as exc:
        return jsonify(error=str(exc)), 422

def worker(job_id, url, fmt, progress=None, cancel_event=None):
    try:
        opts = options()
        opts.update(retries=3, fragment_retries=3)
        if cancel_event:
            def hook(d):
                if cancel_event.is_set():
                    raise RuntimeError("İndirme iptal edildi")
                if progress and d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    progress({"percent": round(100 * d.get("downloaded_bytes", 0) / total, 1) if total else 0,
                              "speed": d.get("speed") or 0})
            opts["progress_hooks"] = [hook]
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

@app.post("/batch")
def batch():
    body = request.get_json(silent=True) or {}
    items = body.get("items", [])
    allowed = {"mp3-128", "mp3-192", "mp3-320", "m4a", "best-mp4", "best-mkv", "best-webm"}
    def format_ok(value):
        if not isinstance(value, str):
            return False
        if value in allowed:
            return True
        parts = value.split("-")
        return len(parts) == 2 and parts[0] in ("mp4", "webm") and parts[1].isdigit() and 0 < int(parts[1]) <= 4320
    if not isinstance(items, list) or not 1 <= len(items) <= 300:
        return jsonify(error="1 ile 300 arasında video seçin."), 400
    if any(not isinstance(item, dict) or not valid_url(item.get("url")) or not format_ok(item.get("format_id")) for item in items):
        return jsonify(error="Geçersiz video veya format."), 400
    job_id = uuid.uuid4().hex
    with lock:
        jobs[job_id] = {"status": "running", "total": len(items), "completed": 0, "failed": 0, "current": ""}
    cancel_event = threading.Event()
    with lock:
        cancel_events[job_id] = cancel_event
        jobs[job_id].update(active=[], percent=0, speed=0, cancelled=0, results={})
    def run_batch():
        errors = []
        active = {}
        def one(index, item):
            if cancel_event.is_set():
                return "cancelled", ""
            with lock:
                jobs[job_id]["results"][str(index)] = {"status": "downloading"}
            sub_id = uuid.uuid4().hex
            def progress(data):
                with lock:
                    active[index] = data
                    jobs[job_id]["active"] = [{"index": k + 1, **v} for k, v in active.items()]
                    jobs[job_id]["speed"] = sum(v.get("speed", 0) for v in active.values())
            for attempt in range(2):
                if cancel_event.is_set():
                    return "cancelled", ""
                worker(sub_id, item["url"], item["format_id"], progress, cancel_event)
                with lock:
                    result = jobs.pop(sub_id, {})
                if result.get("status") == "done":
                    return "done", ""
                error = result.get("error", "Bilinmeyen hata")
                if cancel_event.is_set():
                    return "cancelled", ""
                if attempt == 0:
                    time.sleep(2)
            return "error", error
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(one, i, item): i for i, item in enumerate(items)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    status, error = future.result()
                except Exception as exc:
                    status, error = "error", str(exc)
                with lock:
                    jobs[job_id]["results"][str(index)] = {"status": status, "error": error if status == "error" else ""}
                    active.pop(index, None)
                    jobs[job_id]["active"] = [{"index": k + 1, **v} for k, v in active.items()]
                    jobs[job_id]["speed"] = sum(v.get("speed", 0) for v in active.values())
                    if status == "done":
                        jobs[job_id]["completed"] += 1
                    elif status == "cancelled":
                        jobs[job_id]["cancelled"] += 1
                    else:
                        jobs[job_id]["failed"] += 1
                        errors.append(str(index + 1) + ": " + error)
                    finished = jobs[job_id]["completed"] + jobs[job_id]["failed"] + jobs[job_id]["cancelled"]
                    jobs[job_id]["percent"] = round(100 * finished / len(items), 1)
                    jobs[job_id]["current"] = str(finished) + "/" + str(len(items))
        with lock:
            jobs[job_id].update(status="cancelled" if cancel_event.is_set() else "done", current="", active=[], speed=0, errors=errors[:20])
            cancel_events.pop(job_id, None)
    threading.Thread(target=run_batch, daemon=True).start()
    return jsonify(job_id=job_id)

@app.post("/jobs/<job_id>/cancel")
def cancel_job(job_id):
    with lock:
        event = cancel_events.get(job_id)
        if not event:
            return jsonify(error="Aktif toplu görev bulunamadı"), 404
        event.set()
        jobs[job_id]["status"] = "cancelling"
    return jsonify(status="cancelling")

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
