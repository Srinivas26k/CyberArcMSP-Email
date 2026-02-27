# save as send_links.py, fill in the drive links, then run:
# uv run python send_links.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587
SENDER    = "brian.johnson@cyberarcmsp.in"
PASSWORD  = "zxrmbnvpnjpmpdzl"
TO        = "srinivasvarma764@gmail.com"


WIN_INSTALLER_LINK = "https://drive.google.com/drive/folders/1TpmgvTaZBFq6JIXJTZwlCiQrfd2uuo-h?usp=sharing"   # fill in

html = f"""
<p>Hi Srinivas,</p>
<p>Here are the download links for the <strong>CyberArc MSP AI Outreach</strong> desktop app builds:</p>
<ul>
  <li><a href="{WIN_INSTALLER_LINK}">🪟 Windows Installer (.exe)</a> — installs like any Windows app</li>
</ul>
<p>You'll need Python 3.12 + uv installed first:<br>
<code>pip install uv</code></p>
<p>Best,<br>CyberArc MSP</p>
"""

msg = MIMEMultipart("alternative")
msg["Subject"] = "CyberArc MSP AI Outreach — Build Downloads"
msg["From"] = SENDER
msg["To"] = TO
msg.attach(MIMEText(html, "html"))

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
    s.starttls()
    s.login(SENDER, PASSWORD)
    s.send_message(msg)
    print("✅ Email sent!")
