import tempfile
import threading
import unittest
from pathlib import Path

from desktop.conversion import Event, Job, collect_jobs, run_batch, save_markdown, default_output_folder, create_fresh_output


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def create(self, name, content="source"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_automatic_output_uses_source_folder_or_first_file_parent(self):
        first = self.create("a/Đề cương.txt")
        second = self.create("b/Báo cáo.txt")
        self.assertEqual(default_output_folder([first, second]), first.parent / "Markdown")
        self.assertEqual(default_output_folder([], self.root / "a"), first.parent / "Markdown")

    def test_automatic_output_always_creates_a_fresh_folder(self):
        base = self.root / "Markdown"
        base.write_text("existing file", encoding="utf-8")
        first = create_fresh_output(base)
        second = create_fresh_output(base)
        self.assertEqual(first.name, "Markdown (2)")
        self.assertEqual(second.name, "Markdown (3)")
        self.assertTrue(first.is_dir() and second.is_dir())
        self.assertEqual(base.read_text(encoding="utf-8"), "existing file")

    def test_folder_recursion_preserves_structure_and_excludes_output(self):
        self.create("source/top.pdf")
        self.create("source/sub/child.DOCX")
        self.create("source/results/old.docx")
        self.create("source/ignore.exe")
        self.create("source/already.md")
        jobs = collect_jobs([], folder=self.root / "source", output=self.root / "source/results")
        self.assertEqual({str(job.relative).replace("\\", "/") for job in jobs}, {"top.pdf", "sub/child.DOCX"})
        flat = collect_jobs([], folder=self.root / "source", recursive=False)
        self.assertEqual([job.relative.name for job in flat], ["top.pdf"])

    def test_same_source_and_output_folder_keeps_inputs(self):
        path = self.create("same/document.txt")
        jobs = collect_jobs([], folder=path.parent, output=path.parent)
        result = save_markdown(path.parent, jobs[0], "converted")
        self.assertEqual(result.name, "document.md")
        self.assertEqual(path.read_text(), "source")
        self.assertEqual(len(collect_jobs([], folder=path.parent, output=path.parent)), 1)

    def test_output_above_source_does_not_exclude_source_subfolders(self):
        self.create("source/sub/document.txt")
        jobs = collect_jobs([], folder=self.root / "source", output=self.root)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].relative, Path("sub/document.txt"))

    def test_duplicate_inputs_are_deduplicated(self):
        source = self.create("a.txt")
        self.assertEqual(len(collect_jobs([source, source])), 1)

    def test_unsupported_and_missing_explicit_files_report_errors(self):
        with self.assertRaises(ValueError):
            collect_jobs([self.create("bad.exe")])
        with self.assertRaises(ValueError):
            collect_jobs([self.root / "missing.pdf"])
        with self.assertRaises(ValueError):
            collect_jobs([], folder=self.root / "missing")

    def test_unicode_filenames_and_collision_never_overwrite(self):
        source = self.create("Tài liệu.docx")
        output = self.root / "Kết quả"
        output.mkdir()
        existing = output / "Tài liệu.md"
        existing.write_text("original", encoding="utf-8")
        job = Job(source, Path(source.name))
        first = save_markdown(output, job, "Tiếng Việt")
        second = save_markdown(output, job, "Khác")
        self.assertEqual(first.name, "Tài liệu (2).md")
        self.assertEqual(second.name, "Tài liệu (3).md")
        self.assertEqual(existing.read_text(encoding="utf-8"), "original")
        self.assertEqual(first.read_bytes(), "Tiếng Việt\n".encode("utf-8"))

    def test_same_name_from_different_folders_and_extensions_is_safe(self):
        sources = [self.create("a/report.docx"), self.create("b/report.pdf")]
        output = self.root / "out"
        results = [save_markdown(output, job, "result") for job in collect_jobs(sources)]
        self.assertEqual([path.name for path in results], ["report.md", "report (2).md"])

    def test_prevent_relative_path_escape(self):
        source = self.create("a.txt")
        for relative in [Path("../escape.txt"), self.root / "absolute.txt"]:
            with self.assertRaises(ValueError):
                save_markdown(self.root / "output", Job(source, relative), "text")

    def test_progress_counts_success_and_failure_and_continues(self):
        jobs = collect_jobs([self.create("a.txt"), self.create("bad.txt"), self.create("c.txt")])

        class Fake:
            def convert(self, path):
                if path.name == "bad.txt":
                    raise ValueError("bad document")
                return "Nội dung"

        events = []
        run_batch(jobs, self.root / "out", events.append, threading.Event(), Fake)
        results = [event for event in events if event.kind == "result"]
        self.assertEqual([event.percent for event in results], [33, 66, 100])
        self.assertEqual([bool(event.error) for event in results], [False, True, False])
        self.assertEqual((events[-1].succeeded, events[-1].failed), (2, 1))
        self.assertEqual(len(list((self.root / "out").glob("*.md"))), 2)

    def test_cancellation_finishes_current_file_and_retains_partial_progress(self):
        jobs = collect_jobs([self.create("a.txt"), self.create("b.txt")])
        cancel = threading.Event()

        class Fake:
            def convert(self, path):
                cancel.set()
                return "current file finished"

        events = []
        run_batch(jobs, self.root / "out", events.append, cancel, Fake)
        self.assertEqual(events[-1].percent, 50)
        self.assertTrue(events[-1].cancelled)
        self.assertEqual(events[-1].succeeded, 1)
        self.assertTrue((self.root / "out/a.md").is_file())
        self.assertFalse((self.root / "out/b.md").exists())

    def test_empty_batch_does_not_initialize_backend_or_claim_100_percent(self):
        def unexpected():
            self.fail("backend should not be initialized")

        events = []
        run_batch([], self.root / "out", events.append, threading.Event(), unexpected)
        self.assertEqual(events[-1].kind, "done")
        self.assertEqual(events[-1].percent, 0)
        self.assertFalse((self.root / "out").exists())

    def test_initialization_failure_is_a_fatal_event(self):
        def broken():
            raise ImportError("missing converter")

        events = []
        run_batch([Job(self.create("a.txt"), Path("a.txt"))], self.root / "out", events.append, threading.Event(), broken)
        self.assertEqual(events[-1].kind, "fatal")
        self.assertIn("missing converter", events[-1].error)
        self.assertEqual(events[-1].percent, 0)

    def test_empty_converted_text_is_not_reported_as_success(self):
        class Empty:
            def convert(self, path):
                return " \n"

        events = []
        jobs = collect_jobs([self.create("empty.txt")])
        run_batch(jobs, self.root / "out", events.append, threading.Event(), Empty)
        self.assertEqual(events[-1].failed, 1)
        self.assertFalse((self.root / "out/empty.md").exists())

    def test_pre_cancelled_batch_does_not_create_files(self):
        cancel = threading.Event()
        cancel.set()
        events = []
        run_batch([Job(self.create("a.txt"), Path("a.txt"))], self.root / "out", events.append, cancel)
        self.assertTrue(events[-1].cancelled)
        self.assertEqual(events[-1].completed, 0)


if __name__ == "__main__":
    unittest.main()
