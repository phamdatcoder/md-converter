"""Native desktop window. All conversion and scanning runs off the UI thread."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import unicodedata
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .conversion import (
    Event, Job, SUPPORTED_EXTENSIONS, ScanCancelled, collect_jobs, run_batch,
    default_output_folder, create_fresh_output,
)

from .studio import COLORS, FONT


@dataclass(frozen=True)
class Scanned:
    jobs: list[Job]


def open_folder(path: Path) -> None:
    if not path.is_dir():
        raise ValueError("Folder kết quả không còn tồn tại.")
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ConverterApp(tk.Tk):
    def __init__(self) -> None:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MDConverter.Studio")
        super().__init__()
        self.title("MD Converter")
        self.geometry("1120x800")
        self.minsize(900, 720)
        self.configure(bg=COLORS["background"])
        self.sources: list[Path] = []
        self.jobs: list[Job] = []
        self.results: dict[str, Event] = {}
        self.row_ids: dict[Path, str] = {}
        self.events: queue.Queue[Event | Scanned] = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = False
        self.close_requested = False
        self.last_output: Path | None = None
        self.active_output: Path | None = None
        self.locked_controls: list[ttk.Widget] = []
        self.mode = tk.StringVar(value="files")
        self.source_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.output_hint = tk.StringVar(value="Để trống: tự tạo folder tại nguồn.\nTên trùng: Markdown (2), (3)…")
        self.list_visible = False
        self.recursive = tk.BooleanVar(value=True)
        self.selection_note = tk.StringVar(value="Chưa chọn file.")
        self.status = tk.StringVar(value="Chọn file hoặc folder để bắt đầu.")
        self.progress_text = tk.StringVar(value="0%")
        self.count_text = tk.StringVar(value="0 / 0 file")
        self.link_text = tk.StringVar(value="Đường dẫn kết quả sẽ xuất hiện sau khi chuyển đổi.")
        self.preview_title = tk.StringVar(value="Nội dung Markdown")
        self._styles()
        self._layout()
        self.output_folder.trace_add("write", lambda *_: self._refresh_output_hint())
        icon = Path(__file__).resolve().parent / "assets" / "md-converter.ico"
        if icon.is_file():
            self.iconbitmap(str(icon))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Control-o>", lambda _: self._choose_source())
        self.after(80, self._poll)

    def _styles(self) -> None:
        from .studio import configure_styles
        configure_styles(self)

    def _layout(self) -> None:
        from .studio import build_layout
        build_layout(self)

    def _change_mode(self) -> None:
        self.sources.clear()
        self.source_folder.set("")
        self.selection_note.set("Chưa chọn folder." if self.mode.get() == "folder" else "Chưa chọn file.")
        self.choose.configure(text="Chọn folder…" if self.mode.get() == "folder" else "Chọn file…")
        self.recursive_check.state(["!disabled"] if self.mode.get() == "folder" else ["disabled"])
        self.file_mode_button.set_selected(self.mode.get() == "files")
        self.folder_mode_button.set_selected(self.mode.get() == "folder")
        self._clear_results()
        self._refresh_output_hint()

    def _toggle_list(self) -> None:
        self.list_visible = not self.list_visible
        if self.list_visible:
            self.panes.insert(0, self.listing, weight=1)
            self.after_idle(lambda: self.panes.sashpos(0, min(310, self.panes.winfo_width() // 2)))
        else:
            self.panes.forget(self.listing)
        self._update_list_button()

    def _update_list_button(self) -> None:
        action = "Ẩn" if self.list_visible else "Hiện"
        self.list_toggle.configure(text=f"{action} danh sách ({len(self.jobs)})")

    def _refresh_output_hint(self) -> None:
        if self.output_folder.get().strip():
            self.output_hint.set("Lưu tại đường dẫn đã chọn.\nFile trùng tên không bị ghi đè.")
            return
        folder = Path(self.source_folder.get()) if self.mode.get() == "folder" and self.source_folder.get() else None
        try:
            default_output_folder(self.sources, folder)
            location = "trong folder nguồn" if folder else "cạnh file đầu tiên"
            self.output_hint.set(f"Tự tạo Markdown {location}.\nTên trùng: Markdown (2), (3)…")
        except ValueError:
            self.output_hint.set("Để trống: tự tạo folder tại nguồn.\nNhiều file: dùng folder file đầu tiên.")

    def _use_auto_output(self) -> None:
        self.output_folder.set("")

    def _choose_source(self) -> None:
        if self.busy:
            return
        if self.mode.get() == "folder":
            selected = filedialog.askdirectory(title="Chọn folder tài liệu")
            if selected:
                self.source_folder.set(selected)
                self.selection_note.set(str(Path(selected)))
                self._clear_results()
        else:
            patterns = " ".join("*" + extension for extension in sorted(SUPPORTED_EXTENSIONS))
            selected = filedialog.askopenfilenames(title="Chọn một hoặc nhiều tài liệu", filetypes=[("Tài liệu hỗ trợ", patterns), ("Tất cả file", "*.*")])
            if selected:
                self.sources = [Path(path) for path in selected]
                self.selection_note.set(str(self.sources[0]) if len(self.sources) == 1 else f"Đã chọn {len(self.sources)} file — bấm Chọn file để chọn lại")
                self._clear_results()
                self._display_jobs([Job(path, Path(path.name)) for path in self.sources])
        self._refresh_output_hint()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Chọn folder lưu Markdown")
        if selected:
            self.output_folder.set(str(Path(selected)))

    def _clear_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.results.clear()
        self.row_ids.clear()
        self.jobs.clear()
        self._update_list_button()
        self.last_output = None
        self.open_button.state(["disabled"])
        self.link.configure(fg=COLORS["muted"], cursor="", takefocus=0, font=(FONT, 10))
        self.link_text.set("Đường dẫn kết quả sẽ xuất hiện sau khi chuyển đổi.")
        self.progress.configure(value=0, style="Convert.Horizontal.TProgressbar")
        self.progress_text.set("0%")
        self.count_text.set("0 / 0 file")
        self.status.set("Sẵn sàng chuyển đổi.")
        self.preview_title.set("Nội dung Markdown")
        self._set_preview("Nội dung Markdown sẽ xuất hiện sau khi chuyển đổi.\n\nBật danh sách tài liệu để chọn file cần xem.")

    def _clear(self) -> None:
        self.sources.clear()
        self.source_folder.set("")
        self.selection_note.set("Chưa chọn folder." if self.mode.get() == "folder" else "Chưa chọn file.")
        self._clear_results()
        self._refresh_output_hint()

    def _display_jobs(self, jobs: list[Job]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.row_ids.clear()
        self.jobs = jobs
        for index, job in enumerate(jobs):
            row = str(index)
            self.tree.insert("", "end", iid=row, values=(str(job.relative), "Đang chờ"))
            self.row_ids[job.source] = row
        self._update_list_button()

    def _set_busy(self, value: bool) -> None:
        self.busy = value
        for widget in self.locked_controls:
            widget.state(["disabled"] if value else ["!disabled"])
        if not value and self.mode.get() != "folder":
            self.recursive_check.state(["disabled"])
        self.stop_button.state(["!disabled"] if value else ["disabled"])

    def _start(self) -> None:
        if self.busy:
            return
        if self.mode.get() == "files" and not self.sources:
            messagebox.showinfo("Chọn tài liệu", "Hãy chọn ít nhất một file.")
            return
        if self.mode.get() == "folder" and not self.source_folder.get():
            messagebox.showinfo("Chọn tài liệu", "Hãy chọn folder nguồn.")
            return
        sources = list(self.sources)
        folder = Path(self.source_folder.get()) if self.mode.get() == "folder" else None
        automatic = not self.output_folder.get().strip()
        try:
            output = default_output_folder(sources, folder) if automatic else Path(self.output_folder.get().strip()).expanduser().resolve()
            if not automatic and output.exists() and not output.is_dir():
                raise ValueError("Đường dẫn lưu phải là một folder.")
        except (OSError, ValueError) as error:
            messagebox.showerror("Đường dẫn không hợp lệ", str(error))
            return
        recursive = self.recursive.get()
        self._clear_results()
        self.active_output = output
        self.cancel_event.clear()
        self._set_busy(True)
        self.status.set("Đang quét danh sách tài liệu…")
        self.progress_text.set("Đang quét…")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

        def worker() -> None:
            try:
                jobs = collect_jobs(sources, folder=folder, output=output, recursive=recursive, cancel=self.cancel_event)
                self.events.put(Scanned(jobs))
                destination = output
                if jobs and not self.cancel_event.is_set():
                    if automatic:
                        destination = create_fresh_output(output)
                    else:
                        destination.mkdir(parents=True, exist_ok=True)
                    self.events.put(Event("destination", output=destination))
                run_batch(jobs, destination, self.events.put, self.cancel_event)
            except ScanCancelled:
                self.events.put(Event("done", cancelled=True))
            except Exception as error:
                self.events.put(Event("fatal", error=str(error) or type(error).__name__))

        threading.Thread(target=worker, name="document-converter", daemon=True).start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.stop_button.state(["disabled"])
        self.status.set("Đang dừng… File đang xử lý sẽ được hoàn tất trước khi dừng.")

    def _poll(self) -> None:
        # Bound each tick so a large queue still allows keyboard/window events.
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, Scanned):
                self._display_jobs(event.jobs)
                continue
            self._handle_event(event)
            if self.close_requested and not self.busy:
                self.destroy()
                return
        self.after(80, self._poll)

    def _handle_event(self, event: Event) -> None:
        if event.kind == "destination":
            self.active_output = event.output
        elif event.kind == "start":
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.progress_text.set("0%")
            self.count_text.set(f"0 / {event.total} file")
            self.status.set("Đang khởi tạo bộ chuyển đổi…")
        elif event.kind == "working" and event.job:
            row = self.row_ids[event.job.source]
            self.tree.set(row, "status", "Đang chuyển…")
            self.tree.see(row)
            if not self.cancel_event.is_set():
                self.status.set(f"Đang chuyển: {event.job.relative}")
        elif event.kind == "result" and event.job:
            row = self.row_ids[event.job.source]
            self.results[row] = event
            self.tree.set(row, "status", "Lỗi" if event.error else "Đã lưu")
            self.tree.item(row, tags=("error" if event.error else "success",))
            self.progress.configure(value=event.percent)
            self.progress_text.set(f"{event.percent}%")
            self.count_text.set(f"{event.completed} / {event.total} file")
            if not self.tree.selection() or row in self.tree.selection():
                self.tree.selection_set(row)
                self._show_selection()
        elif event.kind in {"done", "fatal"}:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=event.percent)
            self.progress_text.set(f"{event.percent}%")
            self._set_busy(False)
            if event.kind == "fatal":
                self.status.set("Không thể chuyển đổi. Xem chi tiết ở khung bên phải.")
                self.preview_title.set("Chi tiết lỗi")
                self._set_preview(event.error)
            else:
                self.count_text.set(f"{event.completed} / {event.total} file")
                if event.cancelled:
                    self.status.set(f"Đã dừng · {event.succeeded} file đã lưu · {event.failed} lỗi.")
                    for row in self.tree.get_children():
                        if row not in self.results:
                            self.tree.set(row, "status", "Chưa xử lý")
                elif not event.total:
                    self.status.set("Không tìm thấy file được hỗ trợ trong folder đã chọn.")
                else:
                    self.status.set(f"Đã xử lý xong · {event.succeeded} file đã lưu · {event.failed} lỗi.")
                    if event.failed == 0:
                        self.progress.configure(style="Done.Horizontal.TProgressbar")
                if event.succeeded and self.active_output:
                    self.last_output = self.active_output
                    self.link_text.set(str(self.last_output))
                    self.link.configure(fg=COLORS["accent"], cursor="hand2", takefocus=1, font=(FONT, 10, "underline"))
                    self.open_button.state(["!disabled"])

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", unicodedata.normalize("NFC", text))
        self.preview.configure(state="disabled")

    def _show_selection(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        result = self.results.get(selected[0])
        if result is None:
            job = self.jobs[int(selected[0])]
            self._set_preview(f"File nguồn: {job.source}\n\nChưa có kết quả cho file này.")
            return
        if result.error:
            self.preview_title.set("Chi tiết lỗi")
            self._set_preview(f"File nguồn: {result.job.source}\n\n{result.error}")
        elif result.output:
            self.preview_title.set("Nội dung Markdown")
            try:
                with result.output.open("r", encoding="utf-8") as handle:
                    text = handle.read(256_001)
                if len(text) > 256_000:
                    text = text[:256_000] + "\n\n… Bản xem trước được rút gọn; file Markdown đã lưu đầy đủ."
                self._set_preview(f"Đã lưu: {result.output}\n\n{text}")
            except OSError as error:
                self._set_preview(f"Không mở được bản xem trước: {error}")

    def _open_output(self) -> None:
        if self.last_output:
            try:
                open_folder(self.last_output)
            except (OSError, ValueError) as error:
                messagebox.showerror("Không mở được folder", str(error))

    def _close(self) -> None:
        if self.busy:
            self.close_requested = True
            self._cancel()
            self.title("MD Converter — Đang hoàn tất file trước khi đóng…")
        else:
            self.destroy()
