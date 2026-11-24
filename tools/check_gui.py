"""Exercise the actual native window and batch UI with a local text backend.

This checks GUI wiring without installing document libraries. It is not a
substitute for the source/EXE smoke tests with the real MarkItDown converters.
"""

import functools
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
for variable, name in [("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")]:
    path = root / ".build-tools/tcl" / name
    if path.is_dir():
        os.environ[variable] = str(path)

from desktop import gui
from desktop.conversion import run_batch


class LocalTextBackend:
    def convert(self, source):
        time.sleep(0.3)
        if source.name == "Lỗi.txt":
            raise ValueError("File mẫu bị lỗi để kiểm tra giao diện.")
        return source.read_text(encoding="utf-8")


def capture(app, name):
    app.update()
    import ctypes

    # Tk's winfo_id is the client child window; PrintWindow needs its top level.
    ctypes.windll.user32.GetParent.restype = ctypes.c_void_p
    handle = ctypes.windll.user32.GetParent(ctypes.c_void_p(app.winfo_id()))
    from PIL import ImageGrab
    app.lift()
    app.update()
    ImageGrab.grab(window=handle).save(root / ".build-tools" / name)


def wait_until_idle(app):
    deadline = time.monotonic() + 15
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(0.02)
    assert not app.busy, "UI did not finish conversion"
    app.update()


gui.run_batch = functools.partial(run_batch, backend_factory=LocalTextBackend)
with tempfile.TemporaryDirectory(prefix="md-ui-") as temporary:
    folder = Path(temporary)
    source = folder / "Tài liệu"
    source.mkdir()
    (source / "Ghi chú.txt").write_text("# Ghi chú\n\nTiếng Việt được giữ nguyên.\n", encoding="utf-8")
    (source / "Thư mục con").mkdir()
    (source / "Thư mục con/Báo cáo.txt").write_text("# Báo cáo\n\nNội dung tài liệu.\n", encoding="utf-8")
    app = gui.ConverterApp()
    app.update()
    try:
        assert not app.list_visible
        assert str(app.listing) not in app.panes.panes()
        capture(app, "gui-empty.png")
        app.mode.set("folder")
        app._change_mode()
        app.source_folder.set(str(source))
        app.selection_note.set(str(source))
        app.output_folder.set(str(folder / "Kết quả"))
        app._start()
        deadline = time.monotonic() + 10
        while app.busy and not app.results and time.monotonic() < deadline:
            app.update()
            time.sleep(0.02)
        wait_until_idle(app)
        assert app.progress_text.get() == "100%"
        assert len(app.results) == 2
        assert (folder / "Kết quả/Thư mục con/Báo cáo.md").is_file()
        assert app.last_output == folder / "Kết quả"
        assert not app.open_button.instate(["disabled"])
        opened = []
        gui.open_folder = opened.append
        app._open_output()
        assert opened == [folder / "Kết quả"]
        capture(app, "gui-complete.png")
        wide = app.preview.winfo_width()
        app.list_toggle.invoke()
        app.update()
        assert app.list_visible and app.preview.winfo_width() < wide
        capture(app, "gui-list-visible.png")
        app.list_toggle.invoke()
        app.update()
        assert not app.list_visible and app.preview.winfo_width() >= wide

        (source / "Lỗi.txt").write_text("bad", encoding="utf-8")
        app._start()
        wait_until_idle(app)
        assert "1 lỗi" in app.status.get()
        failed_row = next(row for row, event in app.results.items() if event.error)
        app.tree.selection_set(failed_row)
        app._show_selection()
        capture(app, "gui-error.png")

        app.mode.set("files")
        app._change_mode()
        app.sources = [source / "Ghi chú.txt"]
        app.selection_note.set(str(app.sources[0]))
        app._start()
        wait_until_idle(app)
        assert len(app.results) == 1
        assert app.progress_text.get() == "100%"
        assert app.last_output == folder / "Kết quả"
        app.geometry("1000x760")
        app.update()
        assert app.open_button.winfo_rooty() + app.open_button.winfo_height() <= app.winfo_rooty() + app.winfo_height(), "Folder button clipped at minimum window size"
        assert app.preview.winfo_height() >= 150, "Preview clipped at minimum window size"
        capture(app, "gui-minimum.png")

        app.output_folder.set("")
        app._start()
        wait_until_idle(app)
        assert app.last_output == source / "Markdown"
        assert (app.last_output / "Ghi chú.md").is_file()
        app._start()
        wait_until_idle(app)
        assert app.last_output == source / "Markdown (2)"
        assert "Tiếng Việt" in app.preview.get("1.0", "end")

        app._start()
        app._cancel()
        wait_until_idle(app)
        assert "Đã dừng" in app.status.get()
        report = {"passed": True, "checks": ["native window", "folder batch", "file mode", "Unicode", "nested output", "100%", "output link handler", "error state", "cancellation", "minimum window size"]}
        (root / ".build-tools/gui-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Native GUI checks passed")
    finally:
        app.destroy()
