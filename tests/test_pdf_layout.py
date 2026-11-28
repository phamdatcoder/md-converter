import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

from desktop.pdf_layout import harden_text_lines, _table, extract_pdf, convert_pdf


def structured_pdf(target, image_only_first=False):
    """Real PDF exercising bookmarks, fonts, mixed baselines and a false table."""
    import zlib
    image = zlib.compress(bytes([200, 100, 40]) * 4)
    objects = [b"<< /Type /Catalog /Pages 2 0 R /Outlines 7 0 R >>", b"",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
               b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length " + str(len(image)).encode() + b" >>\nstream\n" + image + b"\nendstream",
               b"<< /Type /Outlines /First 8 0 R /Last 8 0 R /Count 1 >>", b""]
    streams = [
        b"BT /F1 12 Tf 72 700 Td (Wrapped heading) Tj ET",
        b"BT /F2 24 Tf 72 700 Td (Wrapped) Tj 0 -28 Td (heading) Tj ET "
        b"BT /F1 12 Tf 72 640 Td (Ordinary body paragraph.) Tj ET "
        b"BT /F3 10 Tf 72 580 Td (SELECT id,) Tj 12 -14 Td (name) Tj -12 -14 Td (FROM users;) Tj ET "
        b"BT /F1 12 Tf 72 520 Td (Use ) Tj /F3 10 Tf (user_id) Tj /F1 12 Tf ( here.) Tj ET "
        b"72 350 400 60 re S 72 380 m 472 380 l S "
        b"BT /F1 12 Tf 84 395 Td (First paragraph in a background box.) Tj ET "
        b"BT /F1 12 Tf 84 365 Td (Second paragraph in that box.) Tj ET "
        b"q 20 0 0 20 300 200 cm /Im1 Do Q",
        b"BT /F1 12 Tf 72 700 Td (Last page body.) Tj ET",
    ]
    if image_only_first:
        streams[0] = b"q 400 0 0 600 72 100 cm /Im1 Do Q"
    children = []
    for number, stream in enumerate(streams, 1):
        if not (number == 1 and image_only_first):
            stream += b" BT /F1 10 Tf 72 770 Td (Recurring Header) Tj ET "
            stream += f"BT /F1 10 Tf 72 20 Td ({number}) Tj ET".encode()
        page_id = len(objects) + 1
        children.append(page_id)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> /XObject << /Im1 6 0 R >> >> /Contents {page_id + 1} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Count 3 /Kids [{' '.join(f'{i} 0 R' for i in children)}] >>".encode()
    objects[7] = f"<< /Title (Wrapped heading) /Parent 7 0 R /Dest [{children[1]} 0 R /XYZ 72 720 0] >>".encode()
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    target.write_bytes(data)
    return target


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


@unittest.skipUnless(importlib.util.find_spec("pdfplumber"), "Requires PDF dependencies")
class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = structured_pdf(Path(cls.temporary.name) / "structure.pdf")
        cls.before = cls.source.read_bytes()
        cls.result = extract_pdf(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_bookmark_recovers_wrapped_heading_only_on_destination_page(self):
        self.assertEqual(self.result.markdown.count("# Wrapped heading"), 1)
        self.assertIn("Wrapped heading", self.result.markdown.split("<!-- PDF page: 2 -->")[0])
        self.assertEqual(self.result.report["pages"][1]["headings"],
                         [{"level": 1, "text": "Wrapped heading", "method": "bookmark"}])

    def test_code_indentation_and_inline_code_survive(self):
        self.assertIn("```text\nSELECT id,\n  name\nFROM users;\n```", self.result.markdown)
        self.assertIn("Use `user_id` here.", self.result.markdown)

    def test_background_rectangles_do_not_turn_prose_into_tables(self):
        self.assertIn("First paragraph in a background box.", self.result.markdown)
        self.assertNotIn("| ---", self.result.markdown)
        self.assertEqual(self.result.report["pages"][1]["tables"], 0)

    def test_headers_and_page_numbers_are_preserved_but_separated_from_body(self):
        self.assertEqual(self.result.markdown.count("<!-- PDF header: Recurring Header -->"), 3)
        for number in range(1, 4):
            self.assertIn(f"<!-- PDF footer: {number} -->", self.result.markdown)

    def test_image_is_embedded_after_text_and_source_remains_unchanged(self):
        self.assertIn("![Hình gốc — trang 2][pdf-image-2-1]", self.result.markdown)
        self.assertIn("[pdf-image-2-1]: data:image/png;base64,iVBOR", self.result.markdown)
        self.assertLess(self.result.markdown.index("Last page body."), self.result.markdown.index("data:image/png"))
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_fallback_is_explicit_when_structural_reader_fails(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        engine = SimpleNamespace(convert_local=lambda path: SimpleNamespace(text_content="Fallback text"))
        with patch("desktop.pdf_layout.extract_pdf", side_effect=ValueError("bad structure")):
            text = convert_pdf(self.source, engine)
        self.assertIn("bộ đọc dự phòng", text)
        self.assertIn("Fallback text", text)

    def test_heading_fonts_work_without_bookmarks(self):
        path = Path(self.temporary.name) / "no-bookmarks.pdf"
        path.write_bytes(self.before.replace(b"/Outlines 7 0 R", b" " * len(b"/Outlines 7 0 R")))
        result = extract_pdf(path)
        self.assertIn("# Wrapped heading", result.markdown)
        self.assertEqual(result.report["pages"][1]["headings"][0]["method"], "font")

    def test_bookmark_heading_is_recognized_even_at_body_font_size(self):
        path = Path(self.temporary.name) / "same-size.pdf"
        path.write_bytes(self.before.replace(b"/F2 24 Tf", b"/F2 12 Tf").replace(b"0 -28 Td", b"0 -14 Td"))
        result = extract_pdf(path)
        self.assertIn("# Wrapped heading", result.markdown)
        self.assertEqual(result.report["pages"][1]["headings"][0]["method"], "bookmark")

    def test_image_only_page_is_preserved_and_marked_for_ocr(self):
        path = structured_pdf(Path(self.temporary.name) / "image-only-first.pdf", image_only_first=True)
        result = extract_pdf(path)
        self.assertEqual(len(result.report["pages"]), 3)
        self.assertEqual(result.report["pages"][0]["warnings"], ["needs_ocr"])
        self.assertEqual(result.report["pages"][0]["images_preserved"], 1)
        self.assertIn("![Hình gốc — trang 1]", result.markdown)
