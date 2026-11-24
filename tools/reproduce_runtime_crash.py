"""Reproduce a shell-extension VC++ DLL conflict in a disposable process."""

import ctypes
import os
import sys
import threading
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "markitdown-main/packages/markitdown/src"))
ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002)
if "--fixed" in sys.argv:
    from desktop.windows_runtime import preload_cpp_runtime

    preload_cpp_runtime()

conflicting_runtime = Path(os.environ["ProgramFiles"]) / "TortoiseGit/bin/MSVCP140.dll"
if not conflicting_runtime.is_file():
    raise SystemExit("The shell-extension runtime used in the reported crash is not installed.")
ctypes.WinDLL(str(conflicting_runtime))


def convert():
    from desktop.conversion import MarkItDownBackend

    engine = MarkItDownBackend()
    text = engine.convert(root / "markitdown-main/packages/markitdown/tests/test_files/test.docx")
    assert text.strip()
    print("Conversion succeeded", flush=True)


def fail_thread(args):
    import traceback

    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    os._exit(1)


threading.excepthook = fail_thread
worker = threading.Thread(target=convert)
worker.start()
worker.join()
