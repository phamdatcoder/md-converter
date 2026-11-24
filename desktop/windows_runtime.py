"""Load our VC++ runtime before Windows file dialogs load shell extensions.

Windows may reuse an already-loaded DLL by basename when resolving imports.
TortoiseGit's shell extension can load an older MSVCP140.dll while a file
dialog is open. ONNX Runtime then crashes on import if it binds to that DLL.
Load the bundled runtime first, before any native file/folder dialog exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

_libraries: list[object] = []
_loaded_paths: list[str] = []


def preload_cpp_runtime() -> list[str]:
    if sys.platform != "win32" or _libraries:
        return list(_loaded_paths)
    import ctypes

    if getattr(sys, "frozen", False):
        directory = Path(sys._MEIPASS)
    else:
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
        if not length or length >= len(buffer):
            raise OSError("Không xác định được folder thư viện Windows.")
        directory = Path(buffer.value)
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll"):
        path = directory / name
        if not path.is_file():
            if name == "msvcp140.dll":
                raise OSError(f"Thiếu thư viện C++ cần thiết: {path}")
            continue
        # Absolute path; dependencies come from this directory or System32.
        library = ctypes.WinDLL(str(path), winmode=0x00000100 | 0x00000800)
        _libraries.append(library)
        _loaded_paths.append(str(path))
    return list(_loaded_paths)
