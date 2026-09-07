#!/bin/bash
#
# Packages the built app for handover, and prints the three ways to get it
# open on a Mac that is not yours.
#
#   ./build/package.sh
#
# Produces dist/Hecate.dmg — the drag-to-Applications window people expect.
# The DMG is for AirDrop/Teams/email. If you are handing the app over in
# person, the USB route below is better, because it avoids the quarantine
# flag entirely rather than working around it.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP="dist/Hecate.app"
DMG="dist/Hecate.dmg"

if [ ! -d "$APP" ]; then
  echo "No $APP — run ./build/build.sh first."
  exit 1
fi

rm -rf dist/dmgroot "$DMG"
mkdir -p dist/dmgroot
cp -R "$APP" dist/dmgroot/
ln -s /Applications dist/dmgroot/Applications

hdiutil create -volname "Hecate" -srcfolder dist/dmgroot \
  -ov -format UDZO "$DMG" >/dev/null
rm -rf dist/dmgroot

# The DMG is a new file, so it carries no signature of its own. Signing it
# ad-hoc keeps the whole chain consistent.
codesign --force --sign - "$DMG"

echo
echo "Built $DMG ($(du -sh "$DMG" | cut -f1))"
cat <<'NOTES'

──────────────────────────────────────────────────────────────────────────
GETTING IT OPEN ON HER MAC

The app is signed, but ad-hoc: valid, with no paid Developer ID behind it.
macOS only objects when a file arrives carrying the com.apple.quarantine
flag, so the routes differ in whether that flag is ever set.

1. USB STICK  — best, no dialogs at all
   The stick must be formatted exFAT or FAT32. Those filesystems cannot
   store extended attributes, so the quarantine flag is dropped in transit.
   Copy Hecate.app onto the stick, then drag it into Applications on her
   Mac. It opens on a double-click like any other app.

2. AIRDROP / TEAMS / EMAIL  — one extra click, once
   The file arrives quarantined. First launch is refused with "Apple could
   not verify Hecate is free of malware".
       System Settings -> Privacy & Security -> scroll down
       -> "Open Anyway" next to Hecate -> Touch ID or password
   Only needed once. This path exists ONLY because the app is ad-hoc
   signed; an unsigned bundle says "is damaged" and offers no way through.

3. IF SOMETHING STILL BLOCKS IT  — you type this, she never does
       xattr -dr com.apple.quarantine /Applications/Hecate.app
   Strips the flag directly. Safe to run even if it was not needed.

WHAT SHE NEEDS TO KNOW
   • Results land in Documents/Hecate, one dated folder per run.
   • The API key is already inside the app. She never enters one.
   • First run on a folder is slow; later runs are cached and quick.
   • Stop is safe: it keeps every file already read.

CHECK HER MAC IS APPLE SILICON FIRST — this build will not run on Intel.
Full step-by-step, including formatting the stick: build/HANDOVER.md
──────────────────────────────────────────────────────────────────────────
NOTES
