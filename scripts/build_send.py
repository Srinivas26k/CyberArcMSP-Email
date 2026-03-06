#!/usr/bin/env python3
"""
scripts/build_send.py
─────────────────────
1. Builds the Windows release  (electron-builder → NSIS .exe + .zip)
2. Builds the Linux release    (electron-builder → .AppImage + .deb)
3. Uploads all artifacts to GoFile.io  (free, no expiry while active)
4. Sends a professional investor / client review email from Brian

SETUP — create  scripts/.build_send.env  (auto git-ignored):
    SENDER_EMAIL=brian@cyberarcmsp.com
    SENDER_PASSWORD=<m365-app-password>
    SENDER_PROVIDER=m365       # m365 | outlook | gmail | resend
    SENDER_NAME=Brian          # display name shown to recipients

USAGE:
    python3 scripts/build_send.py              # full: build → upload → send
    python3 scripts/build_send.py --skip-build # upload + send only (reuse dist/)
    python3 scripts/build_send.py --dry-run    # build only, no upload / email
    python3 scripts/build_send.py --send-only  # skip build + upload, just send
                                               # (requires INSTALLER_URL / ZIP_URL env vars)
    python3 scripts/build_send.py --win-only   # build + upload Windows only
    python3 scripts/build_send.py --linux-only # build + upload Linux only
"""

import http.client
import json
import os
import smtplib
import subprocess
import sys
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
ENV_FILE = Path(__file__).resolve().parent / ".build_send.env"

# ─── Recipients ───────────────────────────────────────────────────────────────
RECIPIENTS = [
    "contact@cyberarcmsp.com",
    "rajesh.viprala@cyberarcmsp.com",
    "cto.srinivas.nampalli@cyberarcmsp.com",
]

# ─── SMTP host lookup ─────────────────────────────────────────────────────────
_SMTP_HOSTS = {
    "m365":    "smtp.office365.com",
    "outlook": "smtp-mail.outlook.com",
    "gmail":   "smtp.gmail.com",
}

RESEND_URL = "https://api.resend.com/emails"

# ─────────────────────────────────────────────────────────────────────────────
# 0.  Config loader
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    # Environment variables override the file
    for key in (
        "SENDER_EMAIL", "SENDER_PASSWORD", "SENDER_PROVIDER",
        "SENDER_NAME",  "RESEND_API_KEY",
        "INSTALLER_URL", "ZIP_URL",        # pre-set when --send-only
    ):
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def require_cfg(cfg: dict, *keys: str) -> None:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        print(f"\n✘  Missing config key(s): {', '.join(missing)}")
        print(f"   Add them to  {ENV_FILE}  or set as env vars.\n")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Windows build
# ─────────────────────────────────────────────────────────────────────────────

def build_windows() -> None:
    print("\n━━━  Building Windows release  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    env = {**os.environ, "CSC_IDENTITY_AUTO_DISCOVERY": "false"}
    subprocess.run(["bun", "run", "dist:win"], cwd=ROOT, env=env, check=True)
    print("  ✓ Windows build complete")


def build_linux() -> None:
    print("\n━━━  Building Linux release  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    subprocess.run(["bun", "run", "dist:linux"], cwd=ROOT, check=True)
    print("  ✓ Linux build complete")


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Artifact discovery
# ─────────────────────────────────────────────────────────────────────────────

def find_artifacts(platform: str = "all") -> dict[str, Path]:
    """Return artifact paths for the requested platform ('win', 'linux', or 'all')."""
    result: dict[str, Path] = {}

    patterns: list[tuple[str, str]] = []
    if platform in ("win", "all"):
        patterns += [
            ("win_installer", "CyberArc Outreach Setup*.exe"),
            ("win_zip",       "CyberArc Outreach-*-win.zip"),
        ]
    if platform in ("linux", "all"):
        patterns += [
            ("linux_appimage", "CyberArc Outreach*.AppImage"),
            ("linux_deb",      "cyberarc-outreach*.deb"),
        ]

    for label, pattern in patterns:
        matches = sorted(
            DIST_DIR.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            result[label] = matches[0]

    if not result:
        raise FileNotFoundError(
            f"No artifacts found in {DIST_DIR}.\n"
            "Run without --skip-build first, or check that electron-builder succeeded."
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Upload to GoFile.io
# ─────────────────────────────────────────────────────────────────────────────

def _gofile_get_server() -> str:
    """Ask GoFile API which upload server to use."""
    req  = urllib.request.Request("https://api.gofile.io/servers",
                                   headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "ok":
        raise RuntimeError(f"GoFile /servers error: {data}")
    # pick first server, e.g. "store1"
    servers = data["data"]["servers"]
    return servers[0]["name"]


def upload_file(path: Path) -> str:
    """
    Upload a file to GoFile.io using multipart/form-data.
    Returns the shareable download-page URL (https://gofile.io/d/XXXXX).
    """
    name    = path.name
    size_mb = path.stat().st_size / 1_048_576

    print(f"  ↑ {name}  ({size_mb:.1f} MB) → GoFile.io …", flush=True)

    server = _gofile_get_server()

    # Build multipart body manually (no external deps)
    boundary = "CyberArcBoundary1234567890"
    ctype    = "application/octet-stream"
    header   = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode()
    footer   = f"\r\n--{boundary}--\r\n".encode()

    with path.open("rb") as fh:
        body = header + fh.read() + footer

    conn = http.client.HTTPSConnection(f"{server}.gofile.io", timeout=600)
    conn.request(
        "POST",
        "/uploadFile",
        body=body,
        headers={
            "Content-Type":   f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    resp = conn.getresponse()
    data = json.loads(resp.read())

    if data.get("status") != "ok":
        raise RuntimeError(f"GoFile upload error: {data}")

    url = data["data"]["downloadPage"]
    print(f"    ✓ {url}")
    return url


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Email
# ─────────────────────────────────────────────────────────────────────────────

def _read_version() -> str:
    pkg = ROOT / "package.json"
    try:
        return json.loads(pkg.read_text())["version"]
    except Exception:
        return "latest"


def build_email(
    sender_name: str,
    installer_url: str | None,
    zip_url: str | None,
    appimage_url: str | None,
    deb_url: str | None,
    version: str,
) -> tuple[str, str, str]:
    """Return (subject, html_body, plain_body)."""

    subject = f"CyberArc Outreach v{version} — Windows & Linux Builds Ready for Review"

    # ── button styles ──────────────────────────────────────────────────────
    btn_base    = ("display:inline-block;padding:14px 28px;border-radius:8px;"
                   "font-size:15px;font-weight:600;text-decoration:none;margin:6px 8px 6px 0;")
    primary_btn  = f'background:#1A56DB;color:#ffffff;{btn_base}'
    outline_btn  = f'background:#f4f6f9;color:#1A56DB;border:2px solid #1A56DB;{btn_base}'
    green_btn    = f'background:#16a34a;color:#ffffff;{btn_base}'
    goutline_btn = f'background:#f0fdf4;color:#16a34a;border:2px solid #16a34a;{btn_base}'

    win_html   = ""
    win_text   = ""
    linux_html = ""
    linux_text = ""

    if installer_url:
        win_html += f'<a href="{installer_url}" style="{primary_btn}">Download Installer (.exe)</a>'
        win_text += f"  Windows Installer (.exe):\n  {installer_url}\n\n"
    if zip_url:
        win_html += f'<a href="{zip_url}" style="{outline_btn}">Portable ZIP (.zip)</a>'
        win_text += f"  Portable ZIP:\n  {zip_url}\n\n"
    if appimage_url:
        linux_html += f'<a href="{appimage_url}" style="{green_btn}">Download AppImage</a>'
        linux_text  += f"  Linux AppImage (portable):\n  {appimage_url}\n\n"
    if deb_url:
        linux_html += f'<a href="{deb_url}" style="{goutline_btn}">.deb Installer</a>'
        linux_text  += f"  Linux .deb (Ubuntu/Debian):\n  {deb_url}\n\n"

    def _section(heading: str, buttons: str) -> str:
        return (
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:24px 28px 18px;margin:0 0 20px;">'
            f'<p style="margin:0 0 14px;font-size:13px;font-weight:700;color:#64748b;'
            f'letter-spacing:.06em;text-transform:uppercase;">{heading}</p>'
            f'{buttons}'
            f'<p style="margin:14px 0 0;font-size:12px;color:#94a3b8;">Hosted on GoFile.io</p>'
            f'</div>'
        )

    downloads_html = ""
    if win_html:
        downloads_html += _section(f"Windows — v{version}", win_html)
    if linux_html:
        downloads_html += _section(f"Linux — v{version}", linux_html)

    downloads_text = ""
    if win_text:
        downloads_text += f"WINDOWS\n{'─'*38}\n{win_text}"
    if linux_text:
        downloads_text += f"LINUX\n{'─'*38}\n{linux_text}"

    # ── full HTML ─────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:32px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);">

  <tr>
    <td style="background:linear-gradient(135deg,#1A56DB 0%,#0d3d9e 100%);padding:36px 40px;">
      <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">
        CyberArc<span style="color:#93c5fd;"> MSP</span>
      </div>
      <div style="font-size:13px;color:#bfdbfe;margin-top:4px;">AI-Powered B2B Outreach Platform</div>
    </td>
  </tr>

  <tr><td style="padding:40px 40px 32px;">
    <p style="margin:0 0 18px;font-size:16px;color:#1e293b;line-height:1.6;">Hi Team,</p>

    <p style="margin:0 0 18px;font-size:15px;color:#374151;line-height:1.7;">
      Sharing the latest builds of <strong>CyberArc Outreach v{version}</strong> for both
      <strong>Windows</strong> and <strong>Linux</strong>. Please install, explore, and share feedback.
    </p>

    <p style="margin:0 0 8px;font-size:15px;color:#374151;">This release includes:</p>
    <ul style="margin:0 0 24px;padding-left:20px;color:#374151;font-size:15px;line-height:1.8;">
      <li>Apollo.io lead search with startup range (1–100 employees)</li>
      <li>AI email generation in JSON-mode — no more parsing crashes</li>
      <li>Outbox sort controls (newest / oldest / pending / failed)</li>
      <li>Sender account shown in each email's send history sidebar</li>
      <li>Encrypted API key vault — no .env files needed</li>
    </ul>

    {downloads_html}

    <p style="margin:0 0 10px;font-size:15px;font-weight:600;color:#1e293b;">Installation</p>
    <table cellpadding="0" cellspacing="0" width="100%" style="margin:0 0 24px;">
      <tr valign="top">
        <td width="48%" style="padding-right:12px;">
          <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#1A56DB;">Windows</p>
          <ol style="margin:0;padding-left:18px;color:#374151;font-size:13px;line-height:1.9;">
            <li>Download the <strong>.exe</strong> installer</li>
            <li>Run and follow the wizard</li>
            <li>Launch from Start Menu — first launch ~60s</li>
          </ol>
        </td>
        <td width="4%"></td>
        <td width="48%">
          <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#16a34a;">Linux (Ubuntu / Debian)</p>
          <ol style="margin:0;padding-left:18px;color:#374151;font-size:13px;line-height:1.9;">
            <li>Download <strong>.deb</strong> or <strong>AppImage</strong></li>
            <li>.deb: <code style="background:#f1f5f9;padding:1px 4px;border-radius:3px;">sudo dpkg -i *.deb</code></li>
            <li>AppImage: <code style="background:#f1f5f9;padding:1px 4px;border-radius:3px;">chmod +x && ./</code></li>
          </ol>
        </td>
      </tr>
    </table>

    <p style="margin:0 0 32px;font-size:15px;color:#374151;line-height:1.7;">
      Please reply with any UI friction, missing features, or investor demo ideas. All feedback welcome!
    </p>

    <table cellpadding="0" cellspacing="0" style="border-top:1px solid #e2e8f0;padding-top:24px;width:100%;">
    <tr><td>
      <p style="margin:0;font-size:15px;font-weight:600;color:#1e293b;">{sender_name}</p>
      <p style="margin:4px 0 0;font-size:13px;color:#64748b;">CyberArc MSP</p>
      <p style="margin:4px 0 0;font-size:13px;"><a href="https://cyberarcmsp.com" style="color:#1A56DB;text-decoration:none;">cyberarcmsp.com</a></p>
    </td></tr>
    </table>
  </td></tr>

  <tr>
    <td style="background:#f8fafc;padding:18px 40px;border-top:1px solid #e2e8f0;">
      <p style="margin:0;font-size:11px;color:#94a3b8;text-align:center;">
        Sent internally. Files on GoFile.io. &copy; 2026 CyberArc MSP.
      </p>
    </td>
  </tr>

</table>
</td></tr></table>
</body></html>"""

    # ── plain-text fallback ────────────────────────────────────────────────
    plain = f"""Hi Team,

Sharing Windows + Linux builds of CyberArc Outreach v{version}.

DOWNLOAD LINKS (GoFile.io)
{'─'*38}
{downloads_text}
INSTALLATION
Windows : run the .exe, launch from Start Menu (~60s first launch)
Linux   : sudo dpkg -i *.deb  OR  chmod +x *.AppImage && ./*.AppImage

Please reply with feedback — any thoughts or feature requests welcome!

Thanks,
{sender_name}
CyberArc MSP — https://cyberarcmsp.com
"""
    return subject, html, plain


def send_via_smtp(
    cfg: dict,
    subject: str,
    html: str,
    plain: str,
) -> None:
    provider = cfg.get("SENDER_PROVIDER", "m365").lower()
    host     = _SMTP_HOSTS.get(provider, _SMTP_HOSTS["m365"])
    sender   = cfg["SENDER_EMAIL"]
    name     = cfg.get("SENDER_NAME", "Brian")
    password = cfg["SENDER_PASSWORD"]

    for recipient in RECIPIENTS:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{name} <{sender}>"
        msg["To"]      = recipient
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))

        with smtplib.SMTP(host, 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())

        print(f"  ✉  Sent → {recipient}")


def send_via_resend(
    cfg: dict,
    subject: str,
    html: str,
    plain: str,
) -> None:
    api_key = cfg["RESEND_API_KEY"]
    sender  = cfg.get("SENDER_EMAIL", "noreply@cyberarcmsp.com")
    name    = cfg.get("SENDER_NAME", "Brian")

    payload = json.dumps({
        "from":    f"{name} <{sender}>",
        "to":      RECIPIENTS,
        "subject": subject,
        "html":    html,
        "text":    plain,
    }).encode()

    req = urllib.request.Request(
        RESEND_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    print(f"  ✉  Sent via Resend — id: {body.get('id', 'ok')}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args       = set(sys.argv[1:])
    skip_build = "--skip-build"  in args
    dry_run    = "--dry-run"     in args
    send_only  = "--send-only"   in args
    win_only   = "--win-only"    in args
    linux_only = "--linux-only"  in args
    platform   = "win" if win_only else ("linux" if linux_only else "all")

    cfg     = load_config()
    version = _read_version()

    # ── Step 1: Build ─────────────────────────────────────────────────────
    if send_only or skip_build:
        print("  Skip build.")
    else:
        if platform in ("win", "all"):
            build_windows()
        if platform in ("linux", "all"):
            build_linux()

    if dry_run:
        print("\n  --dry-run: stopping after build.\n")
        return

    # ── Step 2: Upload ────────────────────────────────────────────────────
    installer_url: str | None = cfg.get("INSTALLER_URL")
    zip_url:       str | None = cfg.get("ZIP_URL")
    appimage_url:  str | None = cfg.get("APPIMAGE_URL")
    deb_url:       str | None = cfg.get("DEB_URL")

    if not send_only:
        print("\n━━━  Uploading artifacts  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        artifacts = find_artifacts(platform)
        if "win_installer"  in artifacts: installer_url = upload_file(artifacts["win_installer"])
        if "win_zip"        in artifacts: zip_url       = upload_file(artifacts["win_zip"])
        if "linux_appimage" in artifacts: appimage_url  = upload_file(artifacts["linux_appimage"])
        if "linux_deb"      in artifacts: deb_url       = upload_file(artifacts["linux_deb"])
    else:
        if not any([installer_url, zip_url, appimage_url, deb_url]):
            print("  --send-only requires at least one URL env var "
                  "(INSTALLER_URL, ZIP_URL, APPIMAGE_URL, DEB_URL).")
            sys.exit(1)

    # ── Step 3: Send email ────────────────────────────────────────────────
    print("\n━━━  Sending review email  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    use_resend = bool(cfg.get("RESEND_API_KEY"))
    if use_resend:
        require_cfg(cfg, "RESEND_API_KEY", "SENDER_EMAIL")
    else:
        require_cfg(cfg, "SENDER_EMAIL", "SENDER_PASSWORD")

    sender_name = cfg.get("SENDER_NAME", "Brian")
    subject, html, plain = build_email(
        sender_name, installer_url, zip_url, appimage_url, deb_url, version
    )

    if use_resend:
        send_via_resend(cfg, subject, html, plain)
    else:
        send_via_smtp(cfg, subject, html, plain)

    print(f"\n  Done — review email sent to {len(RECIPIENTS)} recipients.\n")


if __name__ == "__main__":
    main()
