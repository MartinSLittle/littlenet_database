from __future__ import annotations

from pathlib import Path
import os


spec_file = globals().get("__file__")
if spec_file is None:
    # PyInstaller puede ejecutar el .spec sin definir __file__.
    spec_file = Path.cwd() / "pyinstaller" / "windows_gui.spec"

project_root = Path(spec_file).resolve().parents[1]
src_dir = project_root / "src" / "import_jobs"
entry_script = src_dir / "gui_repairs.py"
build_mode = os.environ.get("LITTLENET_BUILD_MODE", "onedir").strip().lower()
if build_mode not in {"onedir", "onefile"}:
    raise ValueError(f"Modo de build no soportado: {build_mode}")

app_name = "LittlenetDatabaseGUI"
icon_path = project_root / "assets" / "windows" / "app.ico"
icon = str(icon_path) if icon_path.exists() else None


a = Analysis(
    [str(entry_script)],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=build_mode == "onedir",
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

if build_mode == "onedir":
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=app_name,
    )
