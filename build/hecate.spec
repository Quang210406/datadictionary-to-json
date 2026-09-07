# PyInstaller spec for Hecate.app
#
# Run it through build/build.sh, not directly — the key module it expects is
# generated there, and the bundle is ad-hoc signed afterwards.
#
# Two things here are load-bearing:
#
#   pathex includes src/, so the modules main.py imports by bare name
#   ("import assemble") resolve exactly as they do on the command line. They
#   are listed in hiddenimports as well, because PyInstaller cannot see
#   through the sys.path manipulation runner.py performs at import time.
#
#   schemas/ is shipped as data. main.py derives its schema path from its own
#   __file__, which does not survive freezing, so runner.py overrides
#   main.SCHEMA_DIR to point here.

from pathlib import Path

ROOT = Path(SPECPATH).parent

# Every module in src/, read off the directory rather than listed by hand.
#
# The hand-written list had already fallen four modules behind, and the way it
# fails is the worst kind: PyInstaller cannot see through the sys.path
# manipulation runner.py does, so a module missing from here is simply absent
# from the bundle — and the app then dies with an ImportError on the tester's
# machine, having worked perfectly from source on the build machine.
#
# compare.py is deliberately excluded below (it is a developer tool needing a
# hand-built reference), so it is dropped here too rather than being listed as
# a hidden import and then excluded.
SRC_MODULES = sorted(
    path.stem for path in (ROOT / "src").glob("*.py")
    if path.stem not in {"compare", "__init__"})

a = Analysis(
    [str(ROOT / "app" / "main_app.py")],
    pathex=[str(ROOT / "src"), str(ROOT / "app")],
    binaries=[],
    datas=[
        (str(ROOT / "app" / "web"), "app/web"),
        (str(ROOT / "schemas"), "schemas"),
    ],
    hiddenimports=SRC_MODULES + [
        "bundled_key",
        # readers._read_pypdf imports it INSIDE the function, behind a probe,
        # so PyInstaller has no module-level import to follow. Without this the
        # bundle silently ships with no PDF reader at all — the probe returns
        # False and every PDF reports "no reader for .pdf", which looks like a
        # deliberate limitation rather than a packaging mistake.
        "pypdf",
        # pandas' Excel path is reached only through openpyxl at runtime.
        "openpyxl", "openpyxl.workbook",
        "pandas._libs.tslibs.base",
    ],
    hookspath=[],
    runtime_hooks=[],
    # compare.py is a developer tool that needs a hand-built reference
    # workbook; it has no place in an app given to a tester.
    excludes=[
        # compare.py is a developer tool needing a hand-built reference
        # workbook; it has no place in an app given to a tester.
        "compare", "tkinter", "matplotlib", "pytest", "IPython",
        # --- the heavy readers, left OUT on purpose -------------------------
        #
        # .buildvenv contains docling, docling-graph, litellm and torch (1.7 GB,
        # torch alone 582 MB) because they were evaluated there. Freezing them
        # would produce a ~1 GB bundle that STILL does not work offline: the
        # docling models it actually uses live in ~/.cache/huggingface (506 MB)
        # and are downloaded on first use. On the office network — measured at
        # ~30 KB/s — that is about five hours, and most likely a failure.
        #
        # Excluding them is not a downgrade of the code. readers.py and
        # providers.py decide by PROBING what is importable at run time, so a
        # bundle without docling behaves exactly like a pypdf-only install:
        # .pdf reads through pypdf, and .docx/.pptx/.html report "this build
        # has no reader for that format" rather than failing obscurely.
        #
        # To ship the full version instead, delete this block. Nothing else
        # changes — that is the whole point of the probe.
        "torch", "torchvision", "transformers", "scipy", "sklearn",
        "docling", "docling_core", "docling_ibm_models", "docling_parse",
        "docling_graph", "rapidocr", "onnxruntime", "litellm",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Hecate",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window ever appears
    argv_emulation=False,
    target_arch=None,       # host architecture; see build.sh
    codesign_identity=None, # signed after the fact, in build.sh
    entitlements_file=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Hecate",
)

app = BUNDLE(
    coll,
    name="Hecate.app",
    icon=str(ROOT / "build" / "icon.icns"),
    bundle_identifier="com.hecate.datadictionary",
    info_plist={
        "CFBundleName": "Hecate",
        "CFBundleDisplayName": "Hecate",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        # The app reads documentation folders the user picks in an open
        # panel; declaring this keeps the purpose string honest if macOS
        # ever prompts for Documents or Desktop access.
        "NSDesktopFolderUsageDescription":
            "Hecate reads the documentation folder you choose.",
        "NSDocumentsFolderUsageDescription":
            "Hecate reads the documentation folder you choose and writes "
            "its results to Documents/Hecate.",
        "NSDownloadsFolderUsageDescription":
            "Hecate reads the documentation folder you choose.",
    },
)
