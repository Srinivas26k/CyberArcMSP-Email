"""
download_uv.py — Download the uv binary for the target platform.

Usage:
    python3 scripts/download_uv.py linux    # for Linux x64 deb/AppImage
    python3 scripts/download_uv.py win32    # for Windows x64 exe
    python3 scripts/download_uv.py darwin   # for macOS

Output: bundled-uv/uv  (or bundled-uv/uv.exe on Windows)

This is called automatically by the dist:* npm scripts before electron-builder
runs, so the binary is ready to be copied into extraResources.
"""

import json
import os
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "bundled-uv"
OUT_DIR.mkdir(exist_ok=True)

PLATFORM = sys.argv[1] if len(sys.argv) > 1 else sys.platform
if PLATFORM == "linux2":
    PLATFORM = "linux"

ASSETS = {
    "linux":  ("uv-x86_64-unknown-linux-gnu.tar.gz",   "uv"),
    "darwin": ("uv-x86_64-apple-darwin.tar.gz",         "uv"),
    "win32":  ("uv-x86_64-pc-windows-msvc.zip",         "uv.exe"),
}

if PLATFORM not in ASSETS:
    print(f"ERROR: Unknown platform '{PLATFORM}'. Use: linux, darwin, win32")
    sys.exit(1)


def get_latest_version() -> str:
    url = "https://api.github.com/repos/astral-sh/uv/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "cyberarc-build/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["tag_name"]


def download_uv(platform: str) -> None:
    asset_name, binary_name = ASSETS[platform]
    binary_path = OUT_DIR / binary_name

    # Skip if already downloaded and recent
    if binary_path.exists() and binary_path.stat().st_size > 1_000_000:
        print(f"✓ bundled-uv/{binary_name} already exists — skipping download.")
        return

    version = get_latest_version()
    url = (
        f"https://github.com/astral-sh/uv/releases/download/"
        f"{version}/{asset_name}"
    )
    archive_path = OUT_DIR / asset_name

    print(f"Downloading uv {version} for {platform} …")
    print(f"  {url}")

    def _progress(count, block_size, total):
        pct = min(count * block_size * 100 // total, 100)
        print(f"\r  {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, archive_path, _progress)
    print()  # newline after progress

    # ── Extract ────────────────────────────────────────────────────────────
    if asset_name.endswith(".tar.gz"):
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                # The archive has a top-level dir: uv-x86_64-…/uv
                if member.name.endswith("/uv") or member.name == "uv":
                    member.name = binary_name          # flatten to root
                    tf.extract(member, OUT_DIR, set_attrs=False)
                    break

    elif asset_name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".exe") and "uv" in name.lower():
                    data = zf.read(name)
                    binary_path.write_bytes(data)
                    break

    archive_path.unlink(missing_ok=True)

    # ── Make executable ────────────────────────────────────────────────────
    if platform != "win32":
        binary_path.chmod(
            binary_path.stat().st_mode
            | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
        )

    size_mb = binary_path.stat().st_size / 1024 / 1024
    print(f"✅  bundled-uv/{binary_name} ready  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    download_uv(PLATFORM)
