import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

from desktop.pdf_layout import harden_text_lines, _table


class LineBreakTests(unittest.TestCase):
    def test_soft_lines_become_hard_breaks_and_blank_paragraphs_stay(self):
        self.assertEqual(harden_text_lines("First\nSecond\n\nThird\nFourth"),"First\\\nSecond\n\nThird\\\nFourth")

    def test_tables_fences_and_existing_breaks_are_not_changed(self):
        source="| A | B |\n| --- | --- |\n| One | Two |\n\n```python\nx=1\ny=2\n```\n\nFirst\\\nSecond  \nThird"
        self.assertEqual(harden_text_lines(source),source)

    def test_page_separator_and_headings_do_not_join(self):
        self.assertEqual(harden_text_lines("# Header\nBody\nNext\x0cPage two"),"# Header\nBody\\\nNext\n\nPage two")

    def test_single_column_table_remains_valid_markdown(self):
        source="| Header |\n| --- |\n| First<br>Second |"
        self.assertEqual(harden_text_lines(source),source)

    def test_multiline_table_cells_escape_text_without_spreading_rows(self):
        value=_table([["Header", "Other"],["First\nSecond|part", "<literal>"]])
        self.assertIn("First<br>Second\\|part",value)
        self.assertIn("&lt;literal&gt;",value)
        self.assertEqual(len(value.splitlines()),3)

    @unittest.skipUnless(importlib.util.find_spec("pdfplumber"),"Requires PDF dependencies")
    def test_real_pdf_keeps_lines_table_cells_and_page_order(self):
        from desktop.smoke import linebreak_pdf
        from desktop.conversion import MarkItDownBackend
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"markitdown-main/packages/markitdown/src"))
        with tempfile.TemporaryDirectory() as temporary:
            source=linebreak_pdf(Path(temporary)/"lines.pdf")
            before=source.read_bytes()
            result=MarkItDownBackend().convert(source)
            self.assertIn("First line\\\nSecond line\\\nThird line",result)
            self.assertIn("Cell first<br>Cell second",result)
            self.assertLess(result.index("Third line"),result.index("Header 1"))
            self.assertLess(result.index("Other cell"),result.index("Below table"))
            self.assertEqual(result.count("Cell first"),1)
            self.assertEqual(source.read_bytes(),before)
