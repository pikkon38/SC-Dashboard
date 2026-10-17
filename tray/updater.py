"""Checks GitHub Releases for a newer installer and runs it."""
import json
import os
import re
import subprocess
import tempfile
import urllib.request

REPO = "pikkon38/sc-dashboard"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse(v):
    """'v1.2.3' -> (1, 2, 3); anything unparseable sorts lowest."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def latest():
    """Returns {"version", "url", "name", "notes"} for the newest release's installer, or None."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "sc-dashboard-updater"})
    with urllib.request.urlopen(req, timeout=10) as r:
        rel = json.load(r)
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith("-setup.exe")), None)
    if not asset:
        return None
    return {"version": rel["tag_name"].lstrip("v"), "url": asset["browser_download_url"],
            "name": asset["name"], "notes": rel.get("body") or ""}


def newer_than(current):
    """The latest release if it is newer than `current`, else None."""
    rel = latest()
    if rel and parse(rel["version"]) > parse(current):
        return rel
    return None


def download(rel):
    path = os.path.join(tempfile.gettempdir(), rel["name"])
    req = urllib.request.Request(rel["url"], headers={"User-Agent": "sc-dashboard-updater"})
    with urllib.request.urlopen(req, timeout=120) as r, open(path + ".part", "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    os.replace(path + ".part", path)
    return path


def run_installer(path):
    """Starts the installer silently. The caller must quit right after so files can be replaced;
    the installer starts the app again when it's done."""
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
                     close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
