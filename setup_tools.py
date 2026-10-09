#!/usr/bin/env python3
"""Richtet ffmpeg und eine JavaScript-Laufzeit (Deno) für den F4bst3r-YTDL ein.

Fehlt ein Programm, wird es in den Ordner bin/ neben diesem Skript geladen.
Dafür sind keine Admin-Rechte nötig und am System ändert sich nichts.
Der F4bst3r-YTDL findet bin/ automatisch.

Aufruf:  python setup_tools.py [--force]
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = HERE / "bin"
EXE = ".exe" if os.name == "nt" else ""
BTBN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
DENO = "https://github.com/denoland/deno/releases/latest/download/"


def have(name: str) -> bool:
    return bool(shutil.which(name)) or (BIN / (name + EXE)).exists()


def arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def download(url: str, label: str) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "F4bst3r-YTDL-Setup"})
    handle, name = tempfile.mkstemp(prefix="loader-", suffix=Path(url.split("?")[0]).suffix or ".bin")
    with os.fdopen(handle, "wb") as out, urllib.request.urlopen(request, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last = 0, -1
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                if pct != last and pct % 5 == 0:
                    print(f"\r  {label}: {pct:3d} %  ({done / 1e6:.0f} von {total / 1e6:.0f} MB)", end="", flush=True)
                    last = pct
    print()
    return Path(name)


def unpack(archive: Path, wanted: set[str]) -> list[str]:
    """Kopiert die gewünschten Programme (egal in welchem Unterordner) nach bin/."""
    BIN.mkdir(exist_ok=True)
    found: list[str] = []

    def put(base: str, reader) -> None:
        target = BIN / base
        with reader() as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        found.append(base)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                base = Path(info.filename).name
                if not info.is_dir() and base in wanted:
                    put(base, lambda i=info: z.open(i))
    else:
        with tarfile.open(archive) as t:
            for member in t:
                base = Path(member.name).name
                if member.isfile() and base in wanted:
                    put(base, lambda m=member: t.extractfile(m))
    return found


def install_ffmpeg() -> bool:
    system, cpu = platform.system(), arch()
    wanted = {"ffmpeg" + EXE, "ffprobe" + EXE}
    if system == "Windows":
        url = BTBN + ("ffmpeg-master-latest-winarm64-gpl.zip" if cpu == "arm64" else "ffmpeg-master-latest-win64-gpl.zip")
    elif system == "Linux":
        url = BTBN + ("ffmpeg-master-latest-linuxarm64-gpl.tar.xz" if cpu == "arm64" else "ffmpeg-master-latest-linux64-gpl.tar.xz")
    elif system == "Darwin":
        if shutil.which("brew"):
            print("  ffmpeg wird mit Homebrew installiert ...")
            return subprocess.call(["brew", "install", "ffmpeg"]) == 0
        # Statische Builds (Intel, laufen auf Apple-Chips über Rosetta)
        for tool in ("ffmpeg", "ffprobe"):
            archive = download(f"https://evermeet.cx/ffmpeg/getrelease/{tool}/zip", tool)
            try:
                unpack(archive, {tool})
            finally:
                archive.unlink(missing_ok=True)
        return have("ffmpeg") and have("ffprobe")
    else:
        return False
    archive = download(url, "ffmpeg")
    try:
        print("  ffmpeg wird entpackt ...")
        unpack(archive, wanted)
    finally:
        archive.unlink(missing_ok=True)
    return have("ffmpeg") and have("ffprobe")


def install_deno() -> bool:
    system, cpu = platform.system(), arch()
    triples = {
        ("Windows", "x64"): "x86_64-pc-windows-msvc",
        ("Linux", "x64"): "x86_64-unknown-linux-gnu",
        ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
        ("Darwin", "x64"): "x86_64-apple-darwin",
        ("Darwin", "arm64"): "aarch64-apple-darwin",
    }
    triple = triples.get((system, cpu))
    if not triple:
        return False
    archive = download(f"{DENO}deno-{triple}.zip", "Deno")
    try:
        unpack(archive, {"deno" + EXE})
    finally:
        archive.unlink(missing_ok=True)
    return (BIN / ("deno" + EXE)).exists()


def main() -> int:
    force = "--force" in sys.argv
    problems = 0

    if force or not (have("ffmpeg") and have("ffprobe")):
        print("ffmpeg fehlt und wird jetzt eingerichtet (einmalig, ca. 150 MB) ...")
        try:
            ok = install_ffmpeg()
        except Exception as exc:  # noqa: BLE001
            print(f"  Fehler: {exc}")
            ok = False
        if not ok:
            problems += 1
            print("  ffmpeg konnte nicht automatisch eingerichtet werden. Manuell:")
            print("  Windows: winget install Gyan.FFmpeg | Mac: brew install ffmpeg | Linux: sudo apt install ffmpeg")
    else:
        print("ffmpeg: vorhanden")

    if force or not (have("deno") or have("node") or have("bun")):
        print("Deno (für YouTube nötig) fehlt und wird jetzt eingerichtet (einmalig, ca. 40 MB) ...")
        try:
            ok = install_deno()
        except Exception as exc:  # noqa: BLE001
            print(f"  Fehler: {exc}")
            ok = False
        if not ok:
            problems += 1
            print("  Deno konnte nicht automatisch eingerichtet werden. Manuell: https://deno.com")
    else:
        print("JavaScript-Laufzeit: vorhanden")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
