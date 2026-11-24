# PyInstaller one-file build. No COLLECT stage / companion _internal directory.
from pathlib import Path
import ctypes
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH)
datas = [(str(root / "markitdown-main" / "LICENSE"), "licenses/markitdown")]
datas.append((str(root / "desktop/assets/md-converter.ico"), "desktop/assets"))
datas.append((str(root / "desktop/assets/brand-48.png"), "desktop/assets"))
binaries = []
hiddenimports = []
# Include a known compatible C++ runtime at the bundle root. app.py preloads
# these files before file dialogs can load an older shell-extension copy.
system_buffer = ctypes.create_unicode_buffer(32768)
if not ctypes.windll.kernel32.GetSystemDirectoryW(system_buffer, len(system_buffer)):
    raise RuntimeError("Could not locate the Windows runtime directory")
system_directory = Path(system_buffer.value)
for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "MSVCP140_1.dll"):
    runtime = system_directory / name
    if runtime.is_file():
        binaries.append((str(runtime), "."))
    elif name == "msvcp140.dll":
        raise RuntimeError(f"Required C++ runtime missing: {runtime}")
# Magika's ONNX model and runtime DLLs must ship inside the executable.
# Mammoth uses dynamic imports for some document readers.
for package in ("magika", "onnxruntime", "mammoth", "striprtf", "olefile"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
datas += copy_metadata("markitdown", recursive=True)
notices = root / ".build-tools" / "THIRD_PARTY_NOTICES.txt"
if notices.exists():
    datas.append((str(notices), "licenses"))

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root), str(root / "markitdown-main" / "packages" / "markitdown" / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "IPython", "matplotlib", "scipy", "azure", "openai"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MD Converter",
    icon=str(root / "desktop/assets/md-converter.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
