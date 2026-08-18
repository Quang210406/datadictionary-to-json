# Handing Hecate.app to someone else

Written for the person doing the handover, not the person receiving it.

The app is **ad-hoc signed**: the signature is valid, but no paid Apple
Developer ID stands behind it. macOS does not object to that on its own. It
objects to one thing — a file that arrives carrying the `com.apple.quarantine`
extended attribute. Everything below is about controlling whether that
attribute is ever set.

---

## Before the day: check her Mac's chip

**Do this first. It can invalidate everything else.**

The app is built for **Apple Silicon (arm64) only**. On an Intel Mac it will
not launch at all — not a Gatekeeper warning, a hard refusal.

On her Mac:  → About This Mac

| What it says | Verdict |
|---|---|
| Chip: Apple M1 / M2 / M3 / M4 … | Fine, continue |
| Processor: Intel Core … | **Stop.** The current build will not run |

If it is Intel, tell me — the build has to be redone against an x86_64
Python, which means installing one under Rosetta. It is not a flag I can
flip on the existing bundle.

---

## Prepare the USB stick (the route with no dialogs at all)

exFAT and FAT32 cannot store extended attributes. Passing the app through
such a stick strips the quarantine flag in transit, so the app opens on a
double-click with **no warning of any kind**.

Format the stick — this erases it:

1. Open **Disk Utility**
2. **View → Show All Devices**, then select the stick's *top-level* entry
3. **Erase**
4. Format: **exFAT** — Scheme: **GUID Partition Map**

Then copy the app onto it:

```bash
cp -R dist/Hecate.app /Volumes/YOUR_STICK_NAME/
```

Verify the flag is gone before you leave your desk:

```bash
xattr -p com.apple.quarantine /Volumes/YOUR_STICK_NAME/Hecate.app
```

You want it to fail with **"No such xattr"**. That failure is the success
condition. If it prints a value instead, the stick is not exFAT.

---

## At her Mac

1. Plug in the stick.
2. Drag **Hecate.app** from the stick into **Applications**. (Finder sidebar
   → Applications. If she cannot drag into it, her Desktop is fine too — the
   app does not care where it lives.)
3. Double-click it.

It should open straight into the Vietnamese start screen. If it does, you are
finished — skip to *What to tell her*.

### Confirm it is clean (optional, 5 seconds)

```bash
xattr -p com.apple.quarantine /Applications/Hecate.app
```

"No such xattr" means nothing will ever block it.

---

## If you send it remotely instead

AirDrop, Teams, Slack, email and browser downloads **all set the quarantine
flag**. Send `dist/Hecate.dmg`, then she opens the DMG and drags the app to
Applications as usual. First launch is refused.

**What she will see:** a dialog saying macOS *could not verify the app is
free of malware*, offering only **Done** / **Move to Trash**. There is no
"Open Anyway" in that dialog — this is the part that confuses people. Tell
her to press **Done**, not Move to Trash.

**The way through:**

1.  → **System Settings** → **Privacy & Security**
2. Scroll down to the **Security** section
3. A line reads *"Hecate" was blocked to protect your Mac* with an
   **Open Anyway** button
4. Click it, authenticate with Touch ID or password
5. Launch the app again and confirm once more

Needed **once**. After that it opens normally forever.

> This path exists *only because the app is ad-hoc signed*. An unsigned
> bundle produces *"Hecate is damaged and can't be opened"*, whose only
> button is Move to Trash and which has no Open Anyway entry. That is why
> `build.sh` signs even though there is no Developer ID.

---

## The backstop — you type it, she never does

If anything still blocks it, strip the flag directly:

```bash
xattr -dr com.apple.quarantine /Applications/Hecate.app
```

Safe to run even when it was not needed. This is the reason the "no terminal"
requirement is satisfiable: the constraint is on *her*, not on you, and you
only ever do it once at setup.

---

## What to tell her

- **Results** land in **Documents → Hecate**, one dated folder per run,
  each containing `output.xlsx` (the one to open), `output.json` and
  `report.json`.
- **No API key, ever.** It is already inside the app.
- **The first run on a folder is slow** — every file is one AI call. Later
  runs on the same files are almost instant because they are cached.
- **Stop is safe.** Pressing Stop throws away the unfinished dictionary but
  keeps every file already read, so starting again does not re-pay for them.
  It stops after the current file, not instantly.
- **The scan step costs nothing.** Choosing a folder and looking at what is
  in it makes no AI call. Only *Bắt đầu chạy* does.
- **Blanks are not necessarily bugs.** The coverage panel says so explicitly;
  the source documents genuinely do not state everything.

---

## Two things worth knowing yourself

**The cache will hold bank document text on her Mac.** Extractions are cached
verbatim under `~/Library/Application Support/Hecate/cache/`. That is the
same confidentiality class as `.cache/` in this repo. Fine within the team;
worth being deliberate about if the machine is shared or returned.

**The key is extractable from the bundle.** Anyone who unpacks the app can
recover it, and her runs draw on your free-tier quota. Rotate it if the app
travels beyond the team.

---

## Rebuilding later

```bash
./build/build.sh      # freeze + ad-hoc sign  -> dist/Hecate.app
./build/package.sh    # DMG + this checklist  -> dist/Hecate.dmg
```

Build against `.buildvenv`, never `.venv` — see `CLAUDE.md` for why.
