"""Regression check: native dialogs followed by real threaded conversions."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from tkinter import ttk

from .gui import ConverterApp


def _loaded_cpp_runtime() -> str:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    handle = kernel.GetModuleHandleW("msvcp140.dll")
    buffer = ctypes.create_unicode_buffer(32768)
    if not handle or not kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
        raise OSError("The application's C++ runtime has not been preloaded.")
    return buffer.value


def _exercise_file_dialog(app: ConverterApp) -> None:
    """Open the real dialog and cancel only a dialog belonging to this process."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
    user.EnumWindows.argtypes = [callback_type, ctypes.c_ssize_t]
    user.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    found = []

    @callback_type
    def close_dialog(handle, _):
        process = ctypes.c_ulong()
        user.GetWindowThreadProcessId(handle, ctypes.byref(process))
        classname = ctypes.create_unicode_buffer(256)
        user.GetClassNameW(handle, classname, len(classname))
        if process.value == os.getpid() and classname.value == "#32770":
            found.append(True)
            user.PostMessageW(handle, 0x0010, 0, 0)  # WM_CLOSE -> cancel
        return 1

    deadline = time.monotonic() + 10

    def cancel_dialog():
        user.EnumWindows(close_dialog, 0)
        if not found and time.monotonic() < deadline:
            app.after(100, cancel_dialog)

    app.after(750, cancel_dialog)
    app._choose_source()
    if not found:
        raise AssertionError("Native file dialog was not exercised.")


def _wait(app: ConverterApp) -> None:
    deadline = time.monotonic() + 90
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(0.02)
    if app.busy:
        raise TimeoutError("GUI conversion did not finish.")
    app.update()
    errors = [event.error for event in app.results.values() if event.error]
    if errors:
        raise AssertionError("; ".join(errors))
    if app.progress_text.get() != "100%" or not app.last_output:
        raise AssertionError(f"GUI conversion failed: {app.status.get()}")


def _check_compact_settings(app: ConverterApp) -> None:
    previous_geometry=app.geometry()
    previous_note=app.selection_note.get()
    previous_output=app.output_folder.get()
    app.geometry("1000x760")
    app.selection_note.set("D:/" + "Tài liệu tiếng Việt rất dài/" * 24 + "Báo cáo.docx")
    app.output_folder.set("D:/" + "Nơi lưu kết quả/" * 24)
    app.update()
    def check_no_scroll(widget):
        if isinstance(widget,ttk.Scrollbar):
            raise AssertionError("Settings panel must not contain a scrollbar.")
        for child in widget.winfo_children():
            check_no_scroll(child)
    check_no_scroll(app.settings_panel)
    note_bottom=app.settings_note.winfo_rooty()+app.settings_note.winfo_height()
    form_bottom=app.settings_form.winfo_rooty()+app.settings_form.winfo_height()
    if note_bottom > form_bottom:
        raise AssertionError(f"Settings do not fit at minimum size with long paths: note {note_bottom}, form {form_bottom}, requested {app.settings_form.winfo_reqheight()}, actual {app.settings_form.winfo_height()}.")
    app.folder_mode_button.invoke()
    if app.mode.get() != "folder" or app.recursive_check.instate(["disabled"]):
        raise AssertionError("Folder option did not enable the switch.")
    before=app.recursive.get()
    app.recursive_check.invoke()
    if app.recursive.get() == before:
        raise AssertionError("Recursive switch did not toggle.")
    app.recursive_check.invoke()
    app.file_mode_button.invoke()
    before=app.recursive.get()
    app.recursive_check.invoke()
    if not app.recursive_check.instate(["disabled"]) or app.recursive.get() != before:
        raise AssertionError("File mode must disable the recursive switch.")
    if app.file_mode_button.winfo_height() > 34:
        raise AssertionError("Source options are not compact.")
    app.selection_note.set(previous_note)
    app.output_folder.set(previous_output)
    app.geometry(previous_geometry)
    app.update()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--conflicting-runtime", type=Path)
    args = parser.parse_args(argv)
    report = {"passed": False, "checks": [], "errors": []}
    app = None
    try:
        report["runtime_before_dialog"] = _loaded_cpp_runtime()
        if args.conflicting_runtime:
            # Recreate the exact shell-extension load seen in Windows' crash log.
            conflicting = ctypes.WinDLL(str(args.conflicting_runtime.resolve()))
            report["conflicting_runtime_exercised"] = str(args.conflicting_runtime)
        app = ConverterApp()
        app.update()
        _check_compact_settings(app)
        report["checks"].append("compact source options, working switch, settings without scroll at minimum size and long paths")
        if app.list_visible or len(app.panes.panes()) != 1:
            raise AssertionError("Document list must start hidden.")
        wide = app.preview.winfo_width()
        app.list_toggle.invoke()
        app.update()
        if not app.list_visible or app.preview.winfo_width() >= wide:
            raise AssertionError("Show list did not resize the preview.")
        app.list_toggle.invoke()
        app.update()
        report["checks"].append("document list hidden by default; show/hide preserves wide preview")
        _exercise_file_dialog(app)
        report["checks"].append("native file dialog")
        report["runtime_after_dialog"] = _loaded_cpp_runtime()
        if report["runtime_before_dialog"].lower() != report["runtime_after_dialog"].lower():
            raise AssertionError("The file dialog changed the selected C++ runtime.")
        with tempfile.TemporaryDirectory(prefix="md-gui-real-") as temporary:
            output = Path(temporary) / "Kết quả"
            names = ["test.docx", "test.xlsx", "test.xls", "test.pdf", "test.pptx"]
            app.sources = [args.fixtures.resolve() / name for name in names]
            if not all(path.is_file() for path in app.sources):
                raise ValueError("Missing real document fixtures.")
            app.selection_note.set(f"Đã chọn {len(names)} file")
            app.output_folder.set(str(output))
            app.start_button.invoke()
            _wait(app)
            if len(app.results) != len(names) or len(list(output.glob("*.md"))) != len(names):
                raise AssertionError("Some files were not converted from the Start button.")
            report["checks"].append("Start button: DOCX, XLSX, XLS, PDF, PPTX on worker thread")
            source = Path(temporary) / "Tài liệu"
            nested = source / "Thư mục con"
            nested.mkdir(parents=True)
            for name in names[:3]:
                shutil.copyfile(args.fixtures / name, nested / name)
            app.mode.set("folder")
            app._change_mode()
            app.source_folder.set(str(source))
            app.selection_note.set(str(source))
            app.start_button.invoke()
            _wait(app)
            if len(app.results) != 3 or len(list((output / "Thư mục con").glob("*.md"))) != 3:
                raise AssertionError("Recursive folder conversion did not finish.")
            report["checks"].append("Start button: recursive folder with real documents")
            app.output_folder.set("")
            app.start_button.invoke()
            _wait(app)
            if app.last_output != source / "Markdown":
                raise AssertionError("Automatic folder destination is incorrect.")
            app.start_button.invoke()
            _wait(app)
            if app.last_output != source / "Markdown (2)":
                raise AssertionError("Automatic folder was not created fresh.")
            app.mode.set("files")
            app._change_mode()
            vietnamese = source / "Tiếng Việt.txt"
            vietnamese.write_text("Kiểm tra tiếng Việt: Nguyễn Thị Phương Thảo, đường dẫn, chuyển đổi.", encoding="utf-8")
            app.sources = [vietnamese]
            app.start_button.invoke()
            _wait(app)
            if app.last_output != source / "Markdown (3)" or "Nguyễn Thị Phương Thảo" not in app.preview.get("1.0", "end"):
                raise AssertionError("Automatic file destination or Vietnamese preview failed.")
            report["checks"].append("automatic destinations: folder, file, fresh output on repeat; Vietnamese preview")
            report["passed"] = True
    except Exception as error:
        report["errors"].append(str(error))
    finally:
        if app is not None:
            app.destroy()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1
