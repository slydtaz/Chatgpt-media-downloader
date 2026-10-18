# PyInstaller spec: creates ONE native executable (Windows output: .exe).
# Build on the target OS; PyInstaller does not cross-compile Windows from Linux.
from pathlib import Path

ROOT = Path(SPEC).resolve().parent

block_cipher = None

a = Analysis(
    [str(ROOT / "packaged_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "PROJECT_ID"), ".")],
    hiddenimports=[
        "app.bootstrap",
        "app.main",
        "app.gui",
        "app.playlist",
        "app.config",
        "app.dependencies",
        "app.downloader",
        "app.locking",
        "app.logging_utils",
        "app.platform",
        "app.process_utils",
        "app.security",
        "app.uninstall",
        "app.updater",
        "app.app_update",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ChatGPTMediaDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # Windowed app: no persistent CMD/PowerShell console.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
