"""PDF extraction that keeps visible text lines and explicit table-cell breaks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import re
from statistics import median
import unicodedata


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


@dataclass
class PdfResult:
    markdown: str
    report: dict = field(default_factory=dict)


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def _mono(char: dict) -> bool:
    return bool(re.search(r"courier|consolas|mono|menlo|code", char.get("fontname", ""), re.I))


def _visible(chars):
    return [char for char in chars if char["text"].strip()]


def _size(line: dict) -> float:
    counts = Counter(round(c["size"], 1) for c in _visible(line["chars"]))
    return counts.most_common(1)[0][0] if counts else 0


def _is_code(line: dict) -> bool:
    chars = _visible(line["chars"])
    return bool(chars) and sum(_mono(c) for c in chars) / len(chars) >= .6


def _style(char: dict) -> tuple[bool, bool, bool]:
    font = char.get("fontname", "").lower()
    return _mono(char), bool(re.search(r"bold|black|semibold", font)), bool(re.search(r"italic|oblique", font))


def _escape_prose(text: str) -> str:
    return re.sub(r"([\\`*_\[\]])", r"\\\1", escape(text, quote=False))


def _code_span(text: str) -> str:
    runs = re.findall(r"`+", text)
    fence = "`" * (max(map(len, runs), default=0) + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return fence + pad + text + pad + fence


def _line_text(line: dict, *, styled: bool = False, code: bool = False) -> str:
    """Use x positions, including mixed font sizes on the same baseline."""
    chars = sorted(line["chars"], key=lambda c: c["x0"])
    groups = []
    previous = None
    for char in chars:
        text = char["text"]
        if previous is not None and not previous["text"].endswith(" ") and not text.startswith(" "):
            gap = char["x0"] - previous["x1"]
            if gap > max(1, min(char["size"], previous["size"]) * .18):
                width = max(1, previous["x1"] - previous["x0"])
                spaces = " " * (max(1, round(gap / width)) if code else 1)
                if groups and groups[-1][1] == _style(previous):
                    groups[-1] = (groups[-1][0] + spaces, groups[-1][1])
                else:
                    groups.append((spaces, _style(previous)))
        style = _style(char)
        if groups and groups[-1][1] == style:
            groups[-1] = (groups[-1][0] + text, style)
        else:
            groups.append((text, style))
        previous = char
    if not styled:
        return "".join(text for text, _ in groups).strip()
    parts = []
    for text, (mono, bold, italic) in groups:
        core = text.strip()
        if not core:
            parts.append(text)
            continue
        rendered = _code_span(core) if mono else _escape_prose(core)
        if not mono:
            marker = "***" if bold and italic else "**" if bold else "*" if italic else ""
            rendered = marker + rendered + marker
        parts.append(text[:len(text) - len(text.lstrip())] + rendered + text[len(text.rstrip()):])
    return "".join(parts).strip()


def _outline_by_page(document) -> dict:
    """Bookmarks include destination pages: do not turn TOC entries into headings."""
    from pdfminer.pdfdocument import PDFNoOutlines
    from pdfminer.pdftypes import PDFObjRef, resolve1

    page_ids = {page.page_obj.pageid: number for number, page in enumerate(document.pages, 1)}
    result = {}
    try:
        outlines = list(document.doc.get_outlines())
    except PDFNoOutlines:
        return result
    for level, title, dest, action, _ in outlines:
        title = title.strip()
        if not title:
            continue
        try:
            if dest is None and action:
                dest = resolve1(action).get("D")
            if isinstance(dest, (str, bytes)):
                dest = document.doc.get_dest(dest)
            dest = resolve1(dest)
            if isinstance(dest, dict):
                dest = resolve1(dest.get("D"))
            page_ref = dest[0]
            number = page_ids.get(page_ref.objid) if isinstance(page_ref, PDFObjRef) else None
            if number is not None:
                result.setdefault(number, []).append((_normalized(title), min(6, level)))
        except (KeyError, TypeError, IndexError, ValueError):
            # Malformed bookmark destinations must not block the actual content.
            continue
    return result


def _margin_kind(line: dict, height: float) -> str | None:
    if line["bottom"] < height * .075:
        return "header"
    if line["top"] > height * .9:
        return "footer"
    return None


def _profile(document) -> dict:
    sizes, margins = Counter(), Counter()
    outlines = _outline_by_page(document)
    for page in document.pages:
        sizes.update(round(c["size"], 1) for c in _visible(page.chars) if not _mono(c))
        seen = set()
        for line in page.extract_text_lines(x_tolerance=2, y_tolerance=3):
            kind = _margin_kind(line, page.height)
            if kind:
                seen.add((kind, _normalized(line["text"])))
        margins.update(seen)
        page.close()
    body = sizes.most_common(1)[0][0] if sizes else 12
    heading_sizes = sorted((size for size in sizes if size >= body * 1.12), reverse=True)
    return {"body_size": body, "heading_sizes": heading_sizes, "outlines": outlines,
            "margins": {key for key, count in margins.items() if count >= max(3, len(document.pages) * .2)}}


def _borderless_form(page, lines: list, profile: dict) -> str | None:
    """Retain the original form heuristic only for unstructured, non-code PDFs.

    Comparing character inventories prevents the heuristic from discarding text.
    Prose in books must not be sent through a column-alignment form detector.
    """
    if profile["outlines"] or profile["heading_sizes"] or any(_is_code(line) for line in lines):
        return None
    from html import unescape
    from markitdown.converters._pdf_converter import _extract_form_content_from_words

    candidate = _extract_form_content_from_words(page)
    if candidate and "|" in candidate:
        def inventory(text):
            return Counter(c for c in unicodedata.normalize("NFC", unescape(text)) if c.isalnum())
        source = "".join(_line_text(line) for line in lines)
        if not inventory(source) - inventory(candidate):
            return candidate
    return None


def _inside(char, box) -> bool:
    x = (char["x0"] + char["x1"]) / 2
    y = (char["top"] + char["bottom"]) / 2
    left, top, right, bottom = box
    return left <= x <= right and top <= y <= bottom


def _real_tables(page):
    """Background rectangles and single-column prose are not Markdown tables."""
    tables = []
    for table in page.find_tables():
        if len(table.columns) < 2 or len(table.rows) < 2:
            continue
        chars = _visible(c for c in page.chars if _inside(c, table.bbox))
        if chars and sum(_mono(c) for c in chars) / len(chars) >= .6:
            continue
        rows = table.extract(x_tolerance=2, y_tolerance=3)
        if sum(sum(bool(cell and cell.strip()) for cell in row) >= 2 for row in rows) >= 2:
            tables.append((table, rows))
    return tables


def _heading(lines: list, index: int, profile: dict, page_number: int):
    combined = ""
    for end in range(index, min(index + 4, len(lines))):
        line = lines[end]
        if end > index and (line["top"] - lines[end - 1]["bottom"] > _size(lines[index]) or abs(_size(line) - _size(lines[index])) > 1):
            break
        combined = (combined + " " + _line_text(line)).strip()
        for title, level in profile["outlines"].get(page_number, []):
            if _normalized(combined) == title:
                return level, end + 1, combined, "bookmark"
    line = lines[index]
    size = _size(line)
    if size in profile["heading_sizes"] and not _is_code(line):
        end = index + 1
        text = _line_text(line)
        while end < len(lines) and abs(_size(lines[end]) - size) < .5 and lines[end]["top"] - lines[end - 1]["bottom"] < size * .65:
            text += " " + _line_text(lines[end])
            end += 1
        return min(6, profile["heading_sizes"].index(size) + 1), end, text, "font"
    return None


def _render_lines(lines: list, profile: dict, page_number: int, report: dict) -> str:
    output = []
    body = profile["body_size"]
    gaps = sorted(lines[i]["top"] - lines[i - 1]["bottom"] for i in range(1, len(lines))
                  if abs(_size(lines[i]) - body) < 1 and abs(_size(lines[i - 1]) - body) < 1
                  and 0 <= lines[i]["top"] - lines[i - 1]["bottom"] < body * 2)
    paragraph_gap = max(body * .5, (gaps[len(gaps) // 4] if gaps else body * .3) + body * .45)
    right_edge = max((line["x1"] for line in lines), default=0)
    left_edge = min((line["x0"] for line in lines), default=0)
    list_indent = None
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = _heading(lines, index, profile, page_number)
        if heading:
            level, end, text, method = heading
            output.append("\n\n" + "#" * level + " " + _escape_prose(text) + "\n\n")
            report["headings"].append({"level": level, "text": text, "method": method})
            list_indent = None
            index = end
            continue
        if _is_code(line):
            block = [line]
            index += 1
            while index < len(lines) and _is_code(lines[index]) and lines[index]["top"] - block[-1]["bottom"] < max(_size(line) * 4, 36):
                block.append(lines[index])
                index += 1
            origin = min(c["x0"] for item in block for c in _visible(item["chars"]))
            widths = [c["x1"] - c["x0"] for item in block for c in _visible(item["chars"]) if _mono(c) and c["x1"] > c["x0"]]
            width = median(widths) if widths else 6
            code_lines = []
            for i, item in enumerate(block):
                if i and item["top"] - block[i - 1]["top"] > _size(item) * 1.8:
                    code_lines.append("")
                start = min(c["x0"] for c in _visible(item["chars"]))
                code_lines.append(" " * max(0, round((start - origin) / width)) + _line_text(item, code=True))
            text = "\n".join(code_lines)
            fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", text)), default=0))
            output.append("\n\n" + fence + "text\n" + text + "\n" + fence + "\n\n")
            report["code_blocks"] += 1
            list_indent = None
            continue
        new_paragraph = index and line["top"] - lines[index - 1]["bottom"] > paragraph_gap
        if index and not list_indent and lines[index - 1]["x1"] < right_edge - body * 3 and line["x0"] < left_edge + body * .5 and re.search(r"[.!?…:]$", _line_text(lines[index - 1])):
            new_paragraph = True
        if new_paragraph:
            output.append("\n")
            list_indent = None
        text = _line_text(line, styled=True)
        bullet = re.match(r"^[●•▪○]\s*", text)
        if bullet:
            text = "- " + text[bullet.end():]
            list_indent = line["x0"] + body * .4
        elif list_indent is not None and line["x0"] >= list_indent:
            text = "  " + text
        else:
            list_indent = None
        output.append(text + "\n")
        index += 1
    return re.sub(r"\n{3,}", "\n\n", "".join(output)).strip()


def _images(page, definitions: list, report: dict) -> list:
    """Inline data references keep the output portable and put binary data last."""
    import base64
    import io

    events = []
    seen = set()
    for image in page.images:
        box = (max(page.bbox[0], image["x0"]), max(page.bbox[1], image["top"]),
               min(page.bbox[2], image["x1"]), min(page.bbox[3], image["bottom"]))
        if box in seen or box[2] <= box[0] or box[3] <= box[1]:
            continue
        seen.add(box)
        label = f"pdf-image-{page.page_number}-{len(seen)}"
        try:
            rendered = page.crop(box).to_image(resolution=110).original
            buffer = io.BytesIO()
            rendered.save(buffer, format="PNG")
            data = base64.b64encode(buffer.getvalue()).decode("ascii")
            definitions.append(f"[{label}]: data:image/png;base64,{data}")
            text = f"![Hình gốc — trang {page.page_number}][{label}]"
            report["images_preserved"] += 1
        except OSError:
            raise
        except Exception as error:
            text = f"> Không xuất được hình trang {page.page_number}: {_escape_prose(str(error))}. Cần đối chiếu PDF gốc."
            report["warnings"].append("image_export_failed")
        events.append((box[1], box[0], text))
    return events


def extract_pdf(source: Path) -> PdfResult:
    """Recover document structure without inventing or summarizing source text."""
    import pdfplumber

    pages, definitions = [], []
    report = {"source": source.name, "pages": [], "warnings": []}
    with pdfplumber.open(source) as document:
        profile = _profile(document)
        report["body_font_size"] = profile["body_size"]
        report["page_count"] = len(document.pages)
        for page in document.pages:
            item = {"page": page.page_number, "text_characters": len(_visible(page.chars)),
                    "headings": [], "code_blocks": 0, "tables": 0, "headers": [], "footers": [],
                    "images_preserved": 0, "warnings": []}
            try:
                tables = _real_tables(page)
                boxes = [table.bbox for table, _ in tables]
                outside = page.filter(lambda char: not any(_inside(char, box) for box in boxes))
                lines = outside.extract_text_lines(x_tolerance=2, y_tolerance=3)
                body_lines = []
                for line in lines:
                    kind = _margin_kind(line, page.height)
                    text = _line_text(line)
                    if kind and ((kind, _normalized(text)) in profile["margins"] or (kind == "footer" and re.fullmatch(r"\d+", text))):
                        item[kind + "s"].append(text)
                    else:
                        body_lines.append(line)
                events = _images(page, definitions, item)
                for table, rows in tables:
                    events.append((table.bbox[1], table.bbox[0], _table(rows)))
                item["tables"] = len(tables)
                # Split text around table/image events so headings never merge across a figure.
                chunks = [f"<!-- PDF page: {page.page_number} -->"]
                for text in item["headers"]:
                    chunks.append("<!-- PDF header: " + text.replace("--", "—") + " -->")
                form = _borderless_form(page, body_lines, profile) if not tables and not page.images else None
                if form:
                    chunks.append(form)
                    body_lines = []
                    item["borderless_form"] = True
                events.sort(key=lambda event: (event[0], event[1]))
                pending = []
                event_index = 0
                for line in body_lines:
                    while event_index < len(events) and events[event_index][0] <= line["top"]:
                        if pending:
                            chunks.append(_render_lines(pending, profile, page.page_number, item))
                            pending = []
                        chunks.append(events[event_index][2])
                        event_index += 1
                    pending.append(line)
                if pending:
                    chunks.append(_render_lines(pending, profile, page.page_number, item))
                chunks.extend(event[2] for event in events[event_index:])
                if not item["text_characters"]:
                    chunks.append(f"> Trang {page.page_number} không có lớp chữ đọc được. Cần OCR để tìm kiếm hoặc sao chép nội dung trong hình.")
                    item["warnings"].append("needs_ocr")
                for text in item["footers"]:
                    chunks.append("<!-- PDF footer: " + text.replace("--", "—") + " -->")
                pages.append("\n\n".join(chunk for chunk in chunks if chunk))
                report["pages"].append(item)
            finally:
                page.close()
    text = harden_text_lines("\n\n".join(pages))
    if definitions:
        text += "\n\n<!-- Embedded original images; the Markdown viewer must allow data URIs. -->\n\n" + "\n\n".join(definitions)
    return PdfResult(text, report)


def convert_pdf(source: Path, engine) -> str:
    try:
        return extract_pdf(source).markdown
    except OSError:
        raise
    except Exception as error:
        text = engine.convert_local(str(source)).text_content
        if not text.strip():
            raise ValueError("Không tìm thấy chữ trong PDF. PDF scan cần OCR trước khi chuyển đổi.") from error
        warning = "> Không khôi phục được cấu trúc PDF; đã dùng bộ đọc dự phòng. Cần đối chiếu bố cục và hình ảnh với bản gốc.\n\n"
        return warning + harden_text_lines(text)
