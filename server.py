#!/usr/bin/env python3
"""F4bst3r-YTDL: lokaler Server für yt-dlp + ffmpeg.

Der Server lauscht ausschließlich auf 127.0.0.1. Die Oberfläche (index.html)
spricht mit ihm über eine kleine JSON-API. Jeder Aufruf braucht ein Token, das
beim ersten Start in config.js neben dieser Datei abgelegt wird. Fremde
Webseiten können deshalb keine Downloads auf deinem Rechner auslösen.
"""
from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

try:
    import yt_dlp
    from yt_dlp.utils import DownloadCancelled, DownloadError
except ImportError:  # pragma: no cover
    yt_dlp = None

APP_VERSION = "1.0"
HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.js"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

QUALITIES = {"best", 144, 240, 360, 480, 720, 1080, 1440, 2160, 4320}
CONTAINERS = {"mp4", "mkv", "webm"}
AUDIO_FORMATS = {"best", "mp3", "m4a", "opus", "flac", "wav"}
AUDIO_BITRATES = {"best", "128", "192", "256", "320"}


class Settings:
    port = 8765
    token = ""
    out_dir = Path.home() / "Downloads" / "F4bst3r-YTDL"
    parallel = 2
    cookies_browser: str | None = None
    cookies_file: str | None = None
    cookies_auto = True  # bei Anmelde-Aufforderung automatisch Browser-Cookies probieren


CFG = Settings()
COOKIE_BROWSERS = ("firefox", "chrome", "edge", "brave")


# ---------------------------------------------------------------- Werkzeuge

def extend_path() -> None:
    """ffmpeg/deno, die neben dem Skript liegen, werden automatisch gefunden."""
    for folder in (HERE, HERE / "bin", HERE / "ffmpeg", HERE / "ffmpeg" / "bin"):
        if any((folder / name).exists() for name in ("ffmpeg", "ffmpeg.exe", "deno", "deno.exe")):
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


def js_runtime() -> str | None:
    for name in ("deno", "node", "bun"):
        if shutil.which(name):
            return name
    return None


def tools_status() -> dict:
    return {
        "ok": True,
        "version": APP_VERSION,
        "ytdlp": yt_dlp.version.__version__ if yt_dlp else None,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "jsRuntime": js_runtime(),
        "cookies": CFG.cookies_browser or ("Datei" if CFG.cookies_file else None),
        "dir": str(CFG.out_dir),
        "parallel": CFG.parallel,
    }


def clean(msg: object) -> str:
    text = ANSI.sub("", str(msg)).strip()
    return re.sub(r"^ERROR:\s*", "", text)


def friendly(msg: str) -> str:
    low = msg.lower()
    if "requested format is not available" in low:
        return "Dieses Format gibt es für das Video nicht. Wähle „Max“ oder ein anderes Format."
    if "sign in to confirm" in low or "not a bot" in low:
        return ("YouTube verlangt eine Anmeldung. Starte den F4bst3r-YTDL mit "
                "--cookies-from-browser firefox (oder chrome, edge, brave), damit yt-dlp deine Anmeldung nutzt. "
                "Melde dich dafür im Browser bei YouTube an.")
    if "confirm your age" in low or "age-restricted" in low:
        return "Das Video ist altersbeschränkt. Starte den F4bst3r-YTDL mit --cookies-from-browser firefox, um dich anzumelden."
    if "private video" in low:
        return "Das Video ist privat."
    if "video unavailable" in low or "this video is not available" in low:
        return "Das Video ist nicht verfügbar."
    if "unsupported url" in low:
        return "Dieser Link wird nicht unterstützt."
    if "http error 403" in low:
        return ("YouTube hat den Download abgelehnt (403), auch nach einem zweiten Versuch. Starte den F4bst3r-YTDL neu "
                "oder nutze --cookies-from-browser firefox (oder chrome, edge, brave).")
    if "http error 429" in low or "too many requests" in low:
        return "YouTube bremst gerade ab (zu viele Anfragen). Warte ein paar Minuten und versuche es erneut."
    if "ffmpeg" in low and ("not found" in low or "not installed" in low or "aren't installed" in low):
        return "ffmpeg wurde nicht gefunden. Installiere ffmpeg und starte den F4bst3r-YTDL neu."
    if "unable to download webpage" in low or "network is unreachable" in low or "getaddrinfo" in low:
        return "Keine Verbindung zum Server des Videos. Prüfe deine Internetverbindung."
    return msg


def valid_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2000:
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def needs_login(msg: object) -> bool:
    low = str(msg).lower()
    return any(s in low for s in ("sign in to confirm", "not a bot", "confirm your age", "age-restricted"))


def can_try_cookies() -> bool:
    return CFG.cookies_auto and not CFG.cookies_browser and not CFG.cookies_file


def base_opts(browser: str | None = None) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 20,
        "retries": 5,
        "fragment_retries": 5,
        "windowsfilenames": True,
        "trim_file_name": 160,
    }
    runtime = js_runtime()
    if runtime and runtime != "deno":
        opts["js_runtimes"] = {runtime: {}}
    browser = browser or CFG.cookies_browser
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    if CFG.cookies_file:
        opts["cookiefile"] = CFG.cookies_file
    return opts


# -------------------------------------------------------------- Video-Infos

def pick_thumb(info: dict) -> str | None:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = [t for t in (info.get("thumbnails") or []) if t.get("url")]
    return thumbs[-1]["url"] if thumbs else None


def resolution_of(fmt: dict) -> int | None:
    width, height = fmt.get("width"), fmt.get("height")
    if width and height:
        return int(min(width, height))
    return int(height) if height else None


def get_info(url: str) -> dict:
    try:
        return fetch_info(url)
    except Exception as exc:  # noqa: BLE001
        if not (needs_login(clean(exc)) and can_try_cookies()):
            raise
        for browser in COOKIE_BROWSERS:
            try:
                result = fetch_info(url, browser)
            except Exception:  # noqa: BLE001
                continue  # Browser fehlt, Cookies nicht lesbar oder nicht angemeldet
            CFG.cookies_browser = browser
            return result
        raise exc


def fetch_info(url: str, browser: str | None = None) -> dict:
    opts = base_opts(browser)
    opts.update(skip_download=True, noplaylist=True, extract_flat="in_playlist")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("Zu diesem Link gibt es keine Informationen.")

    hint = "list=" in (urlparse(url).query or "")
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        return {
            "kind": "playlist",
            "title": info.get("title") or "Playlist",
            "uploader": info.get("uploader") or info.get("channel"),
            "count": info.get("playlist_count") or len(entries),
            "thumbnail": pick_thumb(info) or (pick_thumb(entries[0]) if entries else None),
        }

    formats = info.get("formats") or []
    video = [f for f in formats if f.get("vcodec") not in (None, "none")]
    heights = sorted({r for r in (resolution_of(f) for f in video) if r})
    top = heights[-1] if heights else None
    fps = max((f.get("fps") or 0 for f in video if resolution_of(f) == top), default=0) if top else 0
    return {
        "kind": "video",
        "title": info.get("title") or "Ohne Titel",
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": pick_thumb(info),
        "heights": heights,
        "maxRes": top,
        "maxFps": int(fps) if fps else None,
        "hasAudio": any(f.get("acodec") not in (None, "none") for f in formats),
        "isLive": bool(info.get("is_live")),
        "playlistHint": hint,
    }


# ------------------------------------------------------------------ Downloads

class Job:
    def __init__(self, url: str, params: dict, title_hint: str):
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.params = params
        self.title = title_hint or url
        self.state = "queued"  # queued | running | done | error | cancelled
        self.phase = "Wartet"
        self.percent = 0.0
        self.speed: float | None = None
        self.eta: int | None = None
        self.item_index: int | None = None
        self.item_count: int | None = None
        self.files: list[Path] = []
        self.errors: list[str] = []
        self.notes: list[str] = []
        self.cookie_browser: str | None = None
        self.error = ""
        self.detail = ""
        self.created = time.time()
        self.cancel = threading.Event()
        self._item_id = None
        self._streams: list[str] = []

    def public(self) -> dict:
        files = []
        for path in list(self.files):
            try:
                files.append({"name": path.name, "size": path.stat().st_size})
            except OSError:
                files.append({"name": path.name, "size": None})
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "params": self.params,
            "state": self.state,
            "phase": self.phase,
            "percent": round(self.percent, 1),
            "speed": self.speed,
            "eta": self.eta,
            "itemIndex": self.item_index,
            "itemCount": self.item_count,
            "files": files,
            "error": self.error,
            "detail": self.detail,
            "notes": list(self.notes),
            "created": self.created,
        }


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()
SLOTS: threading.Semaphore | None = None

PP_PHASES = {
    "Merger": "Video und Ton zusammenführen",
    "ExtractAudio": "Audio umwandeln",
    "Metadata": "Metadaten schreiben",
    "EmbedThumbnail": "Cover einbetten",
    "ThumbnailsConvertor": "Cover umwandeln",
    "MoveFiles": "Datei ablegen",
    "VideoRemuxer": "Umpacken",
    "VideoConvertor": "Umwandeln",
}


class JobLogger:
    def __init__(self, job: Job):
        self.job = job

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.job.errors.append(clean(msg))


def parse_params(body: dict) -> dict:
    mode = body.get("mode")
    if mode not in ("video", "audio"):
        raise ValueError("Modus fehlt.")
    quality = body.get("quality", "best")
    if quality != "best":
        try:
            quality = int(quality)
        except (TypeError, ValueError):
            raise ValueError("Ungültige Qualität.")
    if quality not in QUALITIES:
        raise ValueError("Ungültige Qualität.")
    container = body.get("container", "mp4")
    aformat = body.get("aformat", "mp3")
    abitrate = str(body.get("abitrate", "best"))
    if container not in CONTAINERS or aformat not in AUDIO_FORMATS or abitrate not in AUDIO_BITRATES:
        raise ValueError("Ungültiges Format.")
    return {
        "mode": mode,
        "quality": quality,
        "container": container,
        "compat": bool(body.get("compat", False)),
        "aformat": aformat,
        "abitrate": abitrate,
        "playlist": bool(body.get("playlist", False)),
        "embedMeta": bool(body.get("embedMeta", True)),
        "embedThumb": bool(body.get("embedThumb", True)),
    }


def build_ydl_opts(job: Job, light: bool) -> dict:
    p = job.params
    o = base_opts(job.cookie_browser)
    o["noplaylist"] = not p["playlist"]
    o["paths"] = {"home": str(CFG.out_dir)}
    o["logger"] = JobLogger(job)
    o["progress_hooks"] = [lambda d: on_progress(job, d)]
    o["postprocessor_hooks"] = [lambda d: on_postprocess(job, d)]
    o["post_hooks"] = [lambda path: job.files.append(Path(path))]
    if p["playlist"]:
        o["ignoreerrors"] = "only_download"

    folder = "%(playlist_title&{}/|)s%(playlist_index&{:02d} - |)s"
    pps: list[dict] = []

    if p["mode"] == "video":
        o["outtmpl"] = folder + "%(title)s%(resolution& [{}]|)s.%(ext)s"
        cap = "" if p["quality"] == "best" else f":{p['quality']}"
        if p["container"] == "mp4":
            o["format"] = "bv*+ba/b"
            if p["compat"]:
                o["format_sort"] = ["vcodec:h264", f"res{cap}", "fps", "acodec:aac"]
            else:
                o["format_sort"] = [f"res{cap}", "vcodec:h264", "fps", "acodec:aac"]
        elif p["container"] == "mkv":
            o["format"] = "bv*+ba/b"
            o["format_sort"] = [f"res{cap}", "fps"]
        else:
            o["format"] = "bv*[ext=webm]+ba[ext=webm]/b[ext=webm]"
            o["format_sort"] = [f"res{cap}", "fps"]
        o["merge_output_format"] = p["container"]
        if p["container"] in ("mp4", "mkv"):
            # Falls die Quelle schon ein fertiges Video in anderem Container ist, wird nur umgepackt.
            pps.append({"key": "FFmpegVideoRemuxer", "preferedformat": p["container"]})
        thumb_ok = p["container"] in ("mp4", "mkv")
    else:
        o["outtmpl"] = folder + "%(title)s.%(ext)s"
        o["format"] = "ba/b"
        extract = {"key": "FFmpegExtractAudio", "preferredcodec": p["aformat"]}
        if p["aformat"] in ("mp3", "m4a", "opus"):
            extract["preferredquality"] = "320" if p["abitrate"] == "best" else p["abitrate"]
        thumb_ok = p["aformat"] != "wav"

    want_thumb = p["embedThumb"] and thumb_ok and not light
    if want_thumb:
        o["writethumbnail"] = True
        pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
    if p["mode"] == "audio":
        pps.append(extract)
    if p["embedMeta"] and not light:
        pps.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
    if want_thumb:
        pps.append({"key": "EmbedThumbnail"})
    o["postprocessors"] = pps
    return o


def on_progress(job: Job, d: dict) -> None:
    if job.cancel.is_set():
        raise DownloadCancelled("Abgebrochen")
    info = d.get("info_dict") or {}
    item_id = info.get("id")
    if item_id != job._item_id:
        job._item_id = item_id
        job._streams.clear()
    if info.get("title"):
        job.title = info["title"]
    index = info.get("playlist_index")
    count = info.get("n_entries") or info.get("playlist_count")
    if index and count:
        job.item_index, job.item_count = int(index), int(count)

    name = d.get("filename") or d.get("tmpfilename") or ""
    if name not in job._streams:
        job._streams.append(name)
    stream = job._streams.index(name)
    video_only = info.get("vcodec") not in (None, "none") and info.get("acodec") == "none"
    streams_total = 2 if video_only or stream > 0 else 1
    streams_total = max(streams_total, len(job._streams))

    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    done = d.get("downloaded_bytes") or 0
    if total:
        fraction = done / total
    elif d.get("fragment_count"):
        fraction = (d.get("fragment_index") or 0) / d["fragment_count"]
    else:
        fraction = 0.0
    if d.get("status") == "finished":
        fraction = 1.0
    item = min((stream + fraction) / streams_total, 0.99)
    if job.item_index and job.item_count:
        item = ((job.item_index - 1) + item) / job.item_count
    job.percent = max(job.percent, item * 100)

    if job.params["mode"] == "audio":
        job.phase = "Audio wird geladen"
    elif info.get("vcodec") in (None, "none"):
        job.phase = "Ton wird geladen"
    else:
        job.phase = "Video wird geladen"
    if d.get("status") == "downloading":
        job.speed = d.get("speed")
        job.eta = d.get("eta")


def on_postprocess(job: Job, d: dict) -> None:
    if d.get("status") == "started":
        job.phase = PP_PHASES.get(d.get("postprocessor", ""), "Nachbearbeitung")
        job.speed = None
        job.eta = None


def run_job(job: Job) -> None:
    assert SLOTS is not None
    with SLOTS:
        if job.cancel.is_set():
            job.state, job.phase = "cancelled", "Abgebrochen"
            return
        job.state, job.phase = "running", "Wird vorbereitet"
        try:
            light = False
            retried_403 = False
            cookie_queue: list[str] | None = None
            login_error: Exception | None = None
            while True:
                job.errors.clear()
                job.files.clear()
                job.percent = 0.0
                try:
                    with yt_dlp.YoutubeDL(build_ydl_opts(job, light)) as ydl:
                        ydl.download([job.url])
                    break
                except DownloadCancelled:
                    raise
                except DownloadError as exc:
                    if job.cancel.is_set():
                        raise DownloadCancelled("Abgebrochen")
                    if not retried_403 and "http error 403" in (str(exc) + " ".join(job.errors)).lower():
                        # YouTube lehnt manchmal einen Download-Link ab; ein frischer Versuch holt neue Links.
                        retried_403 = True
                        job.notes.append("YouTube hat den Download-Link abgelehnt (403). Es wurde automatisch ein zweiter Versuch gestartet.")
                        job.phase = "Neuer Versuch (403)"
                        time.sleep(2)
                        continue
                    if cookie_queue is None and needs_login(str(exc) + " ".join(job.errors)) and can_try_cookies():
                        login_error, cookie_queue = exc, list(COOKIE_BROWSERS)
                    if cookie_queue:
                        job.cookie_browser = cookie_queue.pop(0)
                        job.phase = f"Neuer Versuch mit {job.cookie_browser}-Anmeldung"
                        continue
                    if login_error is not None:
                        raise login_error  # kein Browser hat geholfen: ursprüngliche Meldung zeigen
                    wants_embed = job.params["embedMeta"] or job.params["embedThumb"]
                    if not light and wants_embed and "ostprocessing" in str(exc):
                        job.notes.append("Cover und Metadaten konnten nicht eingebettet werden. Die Datei ist ohne sie gespeichert.")
                        job.phase = "Neuer Versuch ohne Cover"
                        light = True
                        continue
                    raise
            if job.cancel.is_set():
                raise DownloadCancelled("Abgebrochen")
            if job.cookie_browser and job.files:
                CFG.cookies_browser = job.cookie_browser
                job.notes.append(f"YouTube wollte eine Anmeldung. Der Download lief mit den Cookies aus {job.cookie_browser}.")
            if not job.files:
                raise RuntimeError(job.errors[0] if job.errors else "Es wurde keine Datei erzeugt.")
            if job.errors:
                job.notes.append(f"{len(job.errors)} Video(s) wurden übersprungen.")
            job.percent, job.speed, job.eta = 100.0, None, None
            job.phase = "Heruntergeladen"
            job.state = "done"
        except DownloadCancelled:
            job.state, job.phase, job.speed, job.eta = "cancelled", "Abgebrochen", None, None
        except Exception as exc:  # noqa: BLE001
            raw = clean(job.errors[-1] if job.errors else exc)
            job.error = friendly(raw)
            if (job.params["mode"] == "video" and job.params["container"] == "webm"
                    and "requested format is not available" in raw.lower()):
                job.error = "WebM gibt es für dieses Video nicht. Nimm MP4 oder MKV."
            job.detail = raw if raw != job.error else ""
            job.state, job.phase, job.speed, job.eta = "error", "Fehlgeschlagen", None, None


def start_job(url: str, params: dict, title_hint: str) -> Job:
    job = Job(url, params, title_hint)
    with JOBS_LOCK:
        JOBS[job.id] = job
        finished = sorted((j for j in JOBS.values() if j.state in ("done", "error", "cancelled")), key=lambda j: j.created)
        for old in finished[:-40]:
            JOBS.pop(old.id, None)
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job


# --------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "F4bst3r-YTDL/" + APP_VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # ruhig bleiben
        pass

    # --- Sicherheit
    def host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{CFG.port}", f"localhost:{CFG.port}", f"[::1]:{CFG.port}")

    def origin(self) -> str | None:
        return self.headers.get("Origin")

    def origin_ok(self) -> bool:
        origin = self.origin()
        return origin is None or origin in ("null", f"http://127.0.0.1:{CFG.port}", f"http://localhost:{CFG.port}")

    def token_ok(self, query: dict) -> bool:
        given = self.headers.get("X-Loader-Token") or (query.get("t") or [""])[0]
        return hmac.compare_digest(given.encode(), CFG.token.encode())

    # --- Antworten
    def send_bytes(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.origin()
        if origin and self.origin_ok():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, data: dict) -> None:
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 16_384:
            raise ValueError("Anfrage zu groß.")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("Ungültige Anfrage.")
        return data

    # --- Routen
    def do_OPTIONS(self):
        if not (self.host_ok() and self.origin_ok()):
            return self.send_json(403, {"error": "Nicht erlaubt."})
        self.send_response(204)
        origin = self.origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Loader-Token")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method: str) -> None:
        try:
            if not self.host_ok() or not self.origin_ok():
                return self.send_json(403, {"error": "Nicht erlaubt."})
            url = urlparse(self.path)
            query = parse_qs(url.query)
            path = url.path

            if method == "GET" and path in ("/", "/index.html"):
                return self.serve_index()
            if method == "GET" and path == "/api/ping":
                return self.send_json(200, {"ok": True})
            if not path.startswith("/api/"):
                return self.send_json(404, {"error": "Nicht gefunden."})
            if not self.token_ok(query):
                return self.send_json(403, {"error": "token"})

            if method == "GET" and path == "/api/status":
                return self.send_json(200, tools_status())
            if method == "GET" and path == "/api/jobs":
                with JOBS_LOCK:
                    jobs = sorted(JOBS.values(), key=lambda j: j.created, reverse=True)
                return self.send_json(200, {"jobs": [j.public() for j in jobs]})
            if method == "GET" and path == "/api/file":
                return self.serve_file(query)
            if method == "POST" and path == "/api/info":
                return self.api_info()
            if method == "POST" and path == "/api/download":
                return self.api_download()
            if method == "POST" and path == "/api/cancel":
                return self.api_cancel()
            if method == "POST" and path == "/api/clear":
                return self.api_clear()
            if method == "POST" and path == "/api/open-folder":
                return self.api_open_folder()
            return self.send_json(404, {"error": "Nicht gefunden."})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            try:
                self.send_json(500, {"error": friendly(clean(exc))})
            except Exception:  # noqa: BLE001
                pass

    def serve_index(self) -> None:
        html = (HERE / "index.html").read_text(encoding="utf-8")
        inline = "<script>window.LOADER_CONFIG = " + json.dumps({"token": CFG.token, "port": CFG.port}) + ";</script>"
        html = html.replace('<script src="config.js"></script>', inline)
        self.send_bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def serve_file(self, query: dict) -> None:
        job = JOBS.get((query.get("id") or [""])[0])
        try:
            path = job.files[int((query.get("i") or ["0"])[0])] if job else None
        except (ValueError, IndexError):
            path = None
        if not path or not path.is_file():
            return self.send_json(404, {"error": "Die Datei gibt es nicht mehr."})
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(path.name))
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile, 1024 * 256)

    def api_info(self) -> None:
        url = str(self.read_json().get("url", "")).strip()
        if not valid_url(url):
            return self.send_json(400, {"error": "Das ist kein gültiger Link."})
        try:
            self.send_json(200, get_info(url))
        except Exception as exc:  # noqa: BLE001
            raw = clean(exc)
            self.send_json(422, {"error": friendly(raw), "detail": raw})

    def api_download(self) -> None:
        body = self.read_json()
        url = str(body.get("url", "")).strip()
        if not valid_url(url):
            return self.send_json(400, {"error": "Das ist kein gültiger Link."})
        if not shutil.which("ffmpeg"):
            return self.send_json(400, {"error": "ffmpeg wurde nicht gefunden. Installiere ffmpeg und starte den F4bst3r-YTDL neu."})
        try:
            params = parse_params(body)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        hint = str(body.get("title", ""))[:200]
        job = start_job(url, params, hint)
        self.send_json(200, {"id": job.id})

    def api_cancel(self) -> None:
        job = JOBS.get(str(self.read_json().get("id", "")))
        if not job:
            return self.send_json(404, {"error": "Download nicht gefunden."})
        job.cancel.set()
        if job.state == "queued":
            job.state, job.phase = "cancelled", "Abgebrochen"
        self.send_json(200, {"ok": True})

    def api_clear(self) -> None:
        with JOBS_LOCK:
            for job_id in [i for i, j in JOBS.items() if j.state in ("done", "error", "cancelled")]:
                JOBS.pop(job_id, None)
        self.send_json(200, {"ok": True})

    def api_open_folder(self) -> None:
        CFG.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(CFG.out_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(CFG.out_dir)])
            else:
                subprocess.Popen(["xdg-open", str(CFG.out_dir)])
        except OSError:
            return self.send_json(500, {"error": "Der Ordner konnte nicht geöffnet werden: " + str(CFG.out_dir)})
        self.send_json(200, {"ok": True})


# ---------------------------------------------------------------------- Start

def write_config() -> str:
    token = None
    if CONFIG_FILE.exists():
        match = re.search(r'token:\s*"([A-Za-z0-9_\-]{20,})"', CONFIG_FILE.read_text(encoding="utf-8"))
        token = match.group(1) if match else None
    token = token or secrets.token_urlsafe(24)
    CONFIG_FILE.write_text(f'window.LOADER_CONFIG = {{ token: "{token}", port: {CFG.port} }};\n', encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    return token


def main() -> int:
    global SLOTS
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(description="F4bst3r-YTDL: lokaler Server für yt-dlp und ffmpeg")
    parser.add_argument("--port", type=int, default=CFG.port)
    parser.add_argument("--dir", default=str(CFG.out_dir), help="Zielordner für Downloads")
    parser.add_argument("--parallel", type=int, default=CFG.parallel, help="gleichzeitige Downloads")
    parser.add_argument("--open", action="store_true", help="Oberfläche im Browser öffnen")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", help="z. B. firefox, chrome, edge, brave")
    parser.add_argument("--cookies", metavar="DATEI", help="cookies.txt im Netscape-Format")
    parser.add_argument("--no-auto-cookies", action="store_true",
                        help="Browser-Cookies nie automatisch probieren, wenn YouTube eine Anmeldung verlangt")
    args = parser.parse_args()

    if yt_dlp is None:
        print("yt-dlp ist nicht installiert. Starte den F4bst3r-YTDL über start.bat / start.command "
              "oder installiere es mit: python -m pip install -U \"yt-dlp[default]\"")
        return 1

    CFG.port = args.port
    CFG.out_dir = Path(args.dir).expanduser().resolve()
    CFG.parallel = max(1, args.parallel)
    CFG.cookies_browser = args.cookies_from_browser
    CFG.cookies_file = args.cookies
    CFG.cookies_auto = not args.no_auto_cookies
    CFG.out_dir.mkdir(parents=True, exist_ok=True)
    SLOTS = threading.Semaphore(CFG.parallel)
    extend_path()
    CFG.token = write_config()

    address = f"http://127.0.0.1:{CFG.port}/"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", CFG.port), Handler)
    except OSError:
        print(f"Port {CFG.port} ist belegt. Läuft der F4bst3r-YTDL schon? Dann öffne {address}")
        if args.open:
            webbrowser.open(address)
        return 1
    server.daemon_threads = True

    status = tools_status()
    print(f"F4bst3r-YTDL {APP_VERSION} läuft auf {address}")
    print(f"  yt-dlp {status['ytdlp']}, ffmpeg {'ok' if status['ffmpeg'] else 'FEHLT'}, "
          f"JavaScript-Laufzeit: {status['jsRuntime'] or 'FEHLT (Deno oder Node.js installieren)'}")
    print(f"  Downloads landen in {CFG.out_dir}")
    print("  Beenden mit Strg+C")
    if args.open:
        threading.Timer(0.6, webbrowser.open, args=(address,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nF4bst3r-YTDL beendet.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
