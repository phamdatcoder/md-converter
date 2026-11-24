"""Run actual converters from source or inside the EXE without opening a window."""

import argparse
import json
import tempfile
import threading
import zipfile
from pathlib import Path

from .conversion import collect_jobs, run_batch


def linebreak_pdf(target: Path) -> Path:
    """Small real PDF with prose lines and a ruled table with a multiline cell."""
    streams=[
        b"BT /F1 12 Tf 72 740 Td (First line) Tj 0 -18 Td (Second line) Tj 0 -18 Td (Third line) Tj ET",
        b"72 500 300 160 re S 222 500 m 222 660 l S 72 580 m 372 580 l S "
        b"BT /F1 12 Tf 84 640 Td (Header 1) Tj ET "
        b"BT /F1 12 Tf 234 640 Td (Header 2) Tj ET "
        b"BT /F1 12 Tf 84 560 Td (Cell first) Tj 0 -18 Td (Cell second) Tj ET "
        b"BT /F1 12 Tf 234 560 Td (Other cell) Tj ET "
        b"BT /F1 12 Tf 72 470 Td (Below table) Tj ET",
    ]
    objects=[b"<< /Type /Catalog /Pages 2 0 R >>",b"",b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    children=[]
    for stream in streams:
        page_id=len(objects)+1;content_id=page_id+1
        children.append(f"{page_id} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode()+stream+b"\nendstream")
    objects[1]=f"<< /Type /Pages /Count {len(children)} /Kids [{' '.join(children)}] >>".encode()
    data=bytearray(b"%PDF-1.4\n")
    offsets=[0]
    for number,obj in enumerate(objects,1):
        offsets.append(len(data));data.extend(f"{number} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    target.write_bytes(data)
    return target


def formatting_samples(root: Path, fixtures: Path) -> list[Path]:
    """Real files verifying rich text survives both source and frozen builds."""
    word=root/"Rich Word.docx"
    xml='''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:rPr><w:color w:val="FF0000"/><w:strike/></w:rPr><w:t>Định dạng</w:t></w:r></w:p></w:body></w:document>'''
    with zipfile.ZipFile(fixtures/"test.docx") as original,zipfile.ZipFile(word,"w") as target:
        for item in original.infolist():
            target.writestr(item,xml.encode() if item.filename=="word/document.xml" else original.read(item))
    html=root/"Rich HTML.html"
    html.write_text('<meta charset="utf-8"><p style="color:red;text-decoration:line-through">Định dạng</p>',encoding="utf-8")
    from openpyxl import Workbook
    from openpyxl.styles import Font
    book=Workbook();book.active["A1"]="Định dạng";book.active["A1"].font=Font(color="FF0000",strike=True)
    excel=root/"Rich Excel.xlsx";book.save(excel);book.close()
    from pptx import Presentation
    from pptx.util import Inches
    from pptx.dml.color import RGBColor
    deck=Presentation();slide=deck.slides.add_slide(deck.slide_layouts[6])
    run=slide.shapes.add_textbox(Inches(1),Inches(1),Inches(4),Inches(2)).text_frame.paragraphs[0].add_run()
    run.text="Định dạng";run.font.color.rgb=RGBColor(255,0,0);run._r.get_or_add_rPr().set("strike","sngStrike")
    slides=root/"Rich PowerPoint.pptx";deck.save(slides)
    return [word,html,excel,slides]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {"passed": False, "checks": [], "errors": []}
    # Files from the upstream repository exercise the real document libraries.
    fixture_names = [
        "test.docx", "test.xlsx", "test.xls", "test.pdf", "test.pptx", "test.epub",
        "test.json", "test_blog.html", "test_notebook.ipynb", "test_rss.xml",
        "test_outlook_msg.msg",
    ]
    try:
        sources = [args.fixtures.resolve() / name for name in fixture_names]
        missing = [str(path) for path in sources if not path.is_file()]
        if missing:
            raise ValueError("Missing smoke fixtures: " + ", ".join(missing))
        with tempfile.TemporaryDirectory(prefix="md-converter-check-") as temporary:
            root = Path(temporary)
            rich_files=formatting_samples(root,args.fixtures.resolve())
            sources.extend(rich_files)
            pdf_lines=linebreak_pdf(root/"PDF line breaks.pdf")
            sources.append(pdf_lines)
            for name, content in {
                "Tiếng Việt.txt": "Nội dung kiểm thử tiếng Việt: Nguyễn Thị Phương Thảo.",
                "sample.csv": "Tên,Giá\nTài liệu,100\n",
                "sample.tsv": "Tên\tGiá\nTài liệu\t100\n",
                "sample.rtf": r"{\rtf1\ansi Hello from RTF\par Second paragraph}",
            }.items():
                path = root / name
                path.write_text(content, encoding="utf-8")
                sources.append(path)
            events = []
            jobs = collect_jobs(sources)
            output = root / "Kết quả"
            run_batch(jobs, output, events.append, threading.Event())
            for event in events:
                if event.kind == "result":
                    report["checks"].append({"file": str(event.job.source), "passed": not event.error, "error": event.error})
                    if event.error:
                        report["errors"].append(f"{event.job.relative}: {event.error}")
                elif event.kind == "fatal":
                    report["errors"].append(event.error)
            final = events[-1]
            if final.kind != "done" or final.percent != 100 or final.succeeded != len(sources):
                report["errors"].append("Batch did not finish every real-file conversion successfully.")
            vietnamese = output / "Tiếng Việt.md"
            if not vietnamese.exists() or "Nguyễn Thị Phương Thảo" not in vietnamese.read_text(encoding="utf-8"):
                report["errors"].append("Vietnamese text was not preserved.")
            for path in rich_files:
                result=output/(path.stem+".md")
                text=result.read_text(encoding="utf-8") if result.exists() else ""
                good='color: #FF0000' in text and '<del>Định dạng</del>' in text and 'MDFMT' not in text
                report["checks"].append({"file":path.name,"passed":good,"check":"font color and strikethrough preserved"})
                if not good:report["errors"].append(f"Rich text formatting lost in {path.name}")
            result=(output/"PDF line breaks.md").read_text(encoding="utf-8") if (output/"PDF line breaks.md").exists() else ""
            good="First line\\\nSecond line\\\nThird line" in result and "Cell first<br>Cell second" in result and "Below table" in result
            report["checks"].append({"file":pdf_lines.name,"passed":good,"check":"PDF hard line breaks and multiline table cell"})
            if not good:report["errors"].append("PDF line breaks or table structure were lost.")
            report["passed"] = not report["errors"]
    except Exception as error:
        report["errors"].append(str(error))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1
