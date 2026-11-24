"""Batch conversion without GUI dependencies; filesystem writes stay here."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


SUPPORTED_EXTENSIONS = frozenset({
    ".doc", ".docx", ".xls", ".xlsx", ".pdf", ".pptx", ".html", ".htm",
    ".xhtml", ".csv", ".tsv", ".txt", ".json", ".xml", ".epub", ".ipynb",
    ".rtf", ".msg",
})


class Converter(Protocol):
    def convert(self, source: Path) -> str: ...


@dataclass(frozen=True)
class Job:
    source: Path
    relative: Path


@dataclass(frozen=True)
class Event:
    kind: str
    completed: int = 0
    total: int = 0
    job: Job | None = None
    output: Path | None = None
    error: str = ""
    succeeded: int = 0
    failed: int = 0
    cancelled: bool = False

    @property
    def percent(self) -> int:
        return min(100, self.completed * 100 // self.total) if self.total else 0


class ScanCancelled(Exception):
    pass


def default_output_folder(sources: list[Path], folder: Path | None = None) -> Path:
    """Use the source folder, or the first selected file's parent for a batch."""
    if folder is not None:
        return folder.resolve() / "Markdown"
    if not sources:
        raise ValueError("Hãy chọn tài liệu trước khi chuyển đổi.")
    return sources[0].resolve().parent / "Markdown"


def create_fresh_output(base: Path) -> Path:
    """Reserve a new output directory atomically, never reuse an older batch."""
    number = 1
    while True:
        target = base if number == 1 else base.with_name(f"{base.name} ({number})")
        try:
            target.mkdir(parents=True, exist_ok=False)
            return target
        except FileExistsError:
            number += 1


def collect_jobs(
    sources: list[Path],
    *,
    folder: Path | None = None,
    output: Path | None = None,
    recursive: bool = True,
    cancel: threading.Event | None = None,
) -> list[Job]:
    """Snapshot input before conversion, excluding a nested destination and links.

    A destination equal to the source folder is safe: .md files are not inputs.
    Traversal errors abort scanning rather than silently omitting documents.
    """
    root = folder.resolve() if folder is not None else None
    destination = output.resolve() if output is not None else None
    exclude_destination = (
        root is not None and destination is not None and destination != root
        and destination.is_relative_to(root)
    )
    seen: set[Path] = set()
    jobs: list[Job] = []

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise ScanCancelled()

    def add(path: Path) -> None:
        check_cancel()
        if path.is_symlink() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        resolved = path.resolve()
        if not resolved.is_file() or resolved in seen:
            return
        seen.add(resolved)
        relative = resolved.relative_to(root) if root else Path(resolved.name)
        jobs.append(Job(resolved, relative))

    if root is not None:
        if not root.is_dir():
            raise ValueError("Folder nguồn không tồn tại hoặc không thể truy cập.")

        def on_error(error: OSError) -> None:
            raise error

        for current, directories, filenames in os.walk(root, followlinks=False, onerror=on_error):
            check_cancel()
            directories[:] = sorted(
                name for name in directories
                if not (Path(current) / name).is_symlink()
                and not (Path(current) / name).is_junction()
                and not (
                    exclude_destination
                    and (Path(current) / name).resolve().is_relative_to(destination)
                )
            ) if recursive else []
            for name in sorted(filenames):
                add(Path(current) / name)
    else:
        for path in sources:
            if not path.is_file():
                raise ValueError(f"File nguồn không tồn tại: {path}")
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"Chưa hỗ trợ định dạng: {path.suffix or path.name}")
            add(path)
    return jobs


def save_markdown(output: Path, job: Job, text: str) -> Path:
    """Create results exclusively: never overwrite an existing file or source.

    report.pdf -> report.md; collisions become report (2).md, report (3).md.
    Exclusive creation also protects against another process writing meanwhile.
    """
    relative = job.relative
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        raise ValueError("Đường dẫn đầu ra không hợp lệ.")
    root = output.resolve()
    parent = root.joinpath(relative.parent)
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.resolve().is_relative_to(root):
        raise ValueError("Folder kết quả trỏ ra ngoài đường dẫn đã chọn.")
    number = 1
    while True:
        suffix = "" if number == 1 else f" ({number})"
        target = parent / f"{relative.stem}{suffix}.md"
        try:
            handle = target.open("x", encoding="utf-8", newline="\n")
        except FileExistsError:
            number += 1
            continue
        try:
            with handle:
                handle.write(text)
                if not text.endswith("\n"):
                    handle.write("\n")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target


class MarkItDownBackend:
    def __init__(self) -> None:
        # Import lazily so the window appears before loading ONNX/pandas/PDF libs.
        from markitdown import MarkItDown

        self.engine = MarkItDown(enable_plugins=False)

    def convert(self, source: Path) -> str:
        if source.suffix.lower() == ".pdf":
            from .pdf_layout import convert_pdf
            return convert_pdf(source,self.engine)
        if source.suffix.lower() in {".docx", ".pptx", ".html", ".htm", ".xhtml"}:
            from .rich_text import convert_rich_document
            return convert_rich_document(self.engine, source)
        if source.suffix.lower() == ".xlsx":
            from .rich_text import convert_xlsx
            return convert_xlsx(source)
        if source.suffix.lower() == ".doc":
            from .legacy_doc import convert_doc

            return convert_doc(source)
        if source.suffix.lower() == ".rtf":
            from striprtf.striprtf import rtf_to_text

            return rtf_to_text(source.read_bytes().decode("latin-1"), errors="replace")
        result = self.engine.convert_local(str(source))
        text = result.text_content
        if not text.strip():
            if source.suffix.lower() == ".pdf":
                raise ValueError("Không tìm thấy chữ trong PDF. PDF scan cần OCR trước khi chuyển đổi.")
            raise ValueError("Không tìm thấy nội dung văn bản trong file.")
        return text


def run_batch(
    jobs: list[Job],
    output: Path,
    emit: Callable[[Event], None],
    cancel: threading.Event,
    backend_factory: Callable[[], Converter] = MarkItDownBackend,
) -> None:
    """Run on a worker thread. Progress counts finished attempts, including errors.

    Cancellation is cooperative between files. Converter libraries do not expose
    a safe way to interrupt the current document, so it is allowed to finish.
    """
    total = len(jobs)
    completed = succeeded = failed = 0
    emit(Event("start", total=total))
    if not total or cancel.is_set():
        emit(Event("done", total=total, cancelled=cancel.is_set()))
        return
    try:
        backend = backend_factory()
    except Exception as error:
        emit(Event("fatal", total=total, error=f"Không khởi tạo được bộ chuyển đổi: {error}"))
        return
    for job in jobs:
        if cancel.is_set():
            break
        emit(Event("working", completed, total, job))
        target = None
        message = ""
        try:
            text = backend.convert(job.source)
            if not text.strip():
                raise ValueError("File không có nội dung văn bản có thể chuyển đổi.")
            target = save_markdown(output, job, text)
            succeeded += 1
        except Exception as error:
            message = str(error) or type(error).__name__
            failed += 1
        completed += 1
        emit(Event(
            "result", completed, total, job, target, message,
            succeeded=succeeded, failed=failed,
        ))
    emit(Event(
        "done", completed, total, succeeded=succeeded, failed=failed,
        cancelled=cancel.is_set() and completed < total,
    ))
