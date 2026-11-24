"""PDF extraction that keeps visible text lines and explicit table-cell breaks."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re


def _cell(value: str | None) -> str:
    text=escape(value or "",quote=False).replace("\\","\\\\").replace("|",r"\|")
    return "<br>".join(text.replace("\r\n","\n").replace("\r","\n").split("\n"))


def _table(rows) -> str:
    if not rows or not any(any(cell for cell in row) for row in rows):
        return ""
    width=max(len(row) for row in rows)
    lines=["| "+" | ".join(_cell(cell) for cell in row+[None]*(width-len(row)))+" |" for row in rows]
    lines.insert(1,"| "+" | ".join(["---"]*width)+" |")
    return "\n".join(lines)


def harden_text_lines(markdown: str) -> str:
    """Make soft prose line ends visible, preserving tables and fenced code.

    This runs AFTER MarkItDown normalization, which strips the two trailing
    spaces normally used for Markdown hard breaks. A backslash survives that
    normalization and does not require an HTML-enabled Markdown viewer.
    """
    lines=markdown.replace("\r\n","\n").replace("\r","\n").replace("\x0c","\n\n").split("\n")
    result=[]
    fence=None
    table_rows=set()
    for index,line in enumerate(lines):
        cells=line.strip().strip("|").split("|")
        if "|" in line and cells and all(re.fullmatch(r"\s*:?-{3,}:?\s*",cell) for cell in cells):
            start=index-1
            while start>=0 and "|" in lines[start] and lines[start].strip():
                table_rows.add(start);start-=1
            end=index
            while end<len(lines) and "|" in lines[end] and lines[end].strip():
                table_rows.add(end);end+=1
    for index,line in enumerate(lines):
        match=re.match(r"^\s{0,3}(`{3,}|~{3,})",line)
        if match:
            marker=match.group(1)
            if fence is None:fence=marker
            elif marker[0]==fence[0] and len(marker)>=len(fence):fence=None
            result.append(line);continue
        following=lines[index+1] if index+1<len(lines) else ""
        structural=re.match(r"^\s{0,3}(?:#{1,6}\s|<!--|(?:[-*_]\s*){3,}$)",line)
        if (fence is None and line.strip() and following.strip() and index not in table_rows
            and not structural and not line.startswith(("    ","\t"))
            and not line.endswith(("\\","  ","<br>","<br/>","<br />"))):
            line+="\\"
        result.append(line)
    return "\n".join(result)


def convert_pdf(source: Path, engine) -> str:
    """Prefer page line geometry; retain ruled tables in the correct page order.

    Existing borderless form detection remains available on pages without ruled
    tables. If geometric extraction fails, use the engine's existing fallback.
    """
    import pdfplumber
    from markitdown.converters._pdf_converter import _extract_form_content_from_words

    pages=[]
    try:
        with pdfplumber.open(source) as document:
            for page in document.pages:
                try:
                    tables=page.find_tables()
                    if tables:
                        boxes=[table.bbox for table in tables]
                        def outside_tables(character):
                            x=(character["x0"]+character["x1"])/2
                            y=(character["top"]+character["bottom"])/2
                            return not any(left<=x<=right and top<=y<=bottom for left,top,right,bottom in boxes)
                        outside=page.filter(outside_tables)
                        events=[]
                        for line in outside.extract_text_lines(x_tolerance=2,y_tolerance=2):
                            if line["text"].strip():
                                events.append((line["top"],line["x0"],line["text"],False))
                        for table in tables:
                            text=_table(table.extract(x_tolerance=2,y_tolerance=2))
                            if text:events.append((table.bbox[1],table.bbox[0],text,True))
                        events.sort(key=lambda event:(event[0],event[1]))
                        chunks=[]
                        for index,(_,_,text,is_table) in enumerate(events):
                            if chunks:
                                previous=events[index-1][3]
                                chunks.append("\n\n" if is_table or previous else "\n")
                            chunks.append(text)
                        content="".join(chunks)
                    else:
                        content=_extract_form_content_from_words(page)
                        if content is None:
                            content=page.extract_text(x_tolerance=2,y_tolerance=2) or ""
                    if content.strip():pages.append(content.strip())
                finally:page.close()
        text="\n\n".join(pages)
        if not text.strip():
            raise ValueError("Không tìm thấy chữ trong PDF. PDF scan cần OCR trước khi chuyển đổi.")
        return harden_text_lines(text)
    except OSError:
        raise
    except Exception:
        # Preserve the mature fallback for PDFs with unsupported layout features.
        text=engine.convert_local(str(source)).text_content
        if not text.strip():
            raise ValueError("Không tìm thấy chữ trong PDF. PDF scan cần OCR trước khi chuyển đổi.")
        return harden_text_lines(text)
