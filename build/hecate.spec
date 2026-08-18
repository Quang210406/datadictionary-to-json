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

SRC_MODULES = ["main", "layout", "catalog", "assemble", "emit", "store",
               "validate", "agent", "extract", "kinds"]

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
        # pandas' Excel path is reached only through openpyxl at runtime.
        "openpyxl", "openpyxl.workbook",
        "pandas._libs.tslibs.base",
    ],
    hookspath=[],
    runtime_hooks=[],
    # compare.py is a developer tool that needs a hand-built reference
    # workbook; it has no place in an app given to a tester.
    excludes=["compare", "tkinter", "matplotlib", "pytest", "IPython"],
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
