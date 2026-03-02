#!/bin/bash
# CyberArc Outreach — Easy Installer
# Double-click this file in your file manager to install the app.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEB_FILE="$(ls "$SCRIPT_DIR"/cyberarc-outreach_*.deb 2>/dev/null | sort -V | tail -1)"

if [ -z "$DEB_FILE" ]; then
  zenity --error --text="Could not find the installer (.deb) file.\nMake sure install.sh is in the same folder as the .deb file." 2>/dev/null \
    || xmessage "Could not find the .deb installer file. Put install.sh in the same folder."
  exit 1
fi

# Ask for confirmation
zenity --question \
  --title="CyberArc Outreach — Install" \
  --text="This will install CyberArc Outreach on your computer.\n\nYour administrator password will be needed.\n\nContinue?" \
  --ok-label="Install" --cancel-label="Cancel" 2>/dev/null
if [ $? -ne 0 ]; then exit 0; fi

# Install using pkexec (GUI password prompt, no terminal needed)
pkexec dpkg -i "$DEB_FILE"

if [ $? -eq 0 ]; then
  zenity --info \
    --title="Installed!" \
    --text="CyberArc Outreach has been installed.\n\nFind it in your Applications menu.\n\n⚠️  First launch takes 1-3 minutes while the app sets up automatically.\nPlease wait — it will open on its own." 2>/dev/null \
    || xmessage "CyberArc Outreach installed! Find it in your Applications menu. First launch takes 1-3 minutes."
else
  zenity --error \
    --title="Installation Failed" \
    --text="Installation failed. Please contact support." 2>/dev/null \
    || xmessage "Installation failed. Please contact support."
fi
