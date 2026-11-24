"""Carry text appearance through the engine without losing document structure.

Temporary opaque markers survive the engine's Markdown escaping. They are
replaced after conversion with safe inline HTML colors or Markdown deletion.
No source document is modified. PDF and legacy binary Office are not covered.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import uuid
import colorsys
import zipfile
from xml.etree import ElementTree as ET
from defusedxml.ElementTree import fromstring

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def safe_color(value: str | None) -> str | None:
    if not value or value.lower() in {"auto", "inherit", "initial", "unset", "currentcolor"}:
        return None
    from PIL import ImageColor
    try:
        rgb = ImageColor.getrgb(value.strip())
        if len(rgb) == 3:
            return "#" + "".join(f"{part:02X}" for part in rgb)
    except (ValueError, TypeError):
        pass
    return None


class FormattingMarkers:
    def __init__(self):
        self.prefix = "MDFMT" + uuid.uuid4().hex.upper()
        self.replacements = {}

    def wrap(self, text: str, color=None, strike=False) -> str:
        if not text.strip() or not (color or strike):
            return text
        left = text[:len(text)-len(text.lstrip())]
        right = text[len(text.rstrip()):]
        body = text.strip()
        start = f"{self.prefix}N{len(self.replacements)}OPEN"
        end = f"{self.prefix}N{len(self.replacements)}CLOSE"
        opening, closing = ("~~", "~~") if strike else ("", "")
        if color:
            opening = f'<span style="color: {color}">' + ("<del>" if strike else "")
            closing = ("</del>" if strike else "") + "</span>"
        self.replacements[start] = opening
        self.replacements[end] = closing
        return left + start + body + end + right

    def restore(self, text: str) -> str:
        if not self.replacements:
            return text
        pattern = re.compile(re.escape(self.prefix) + r"N\d+(?:OPEN|CLOSE)")
        return pattern.sub(lambda match:self.replacements[match.group()], text)


def _theme(archive):
    name = next((name for name in archive.namelist() if name.endswith("theme/theme1.xml")), None)
    if not name:
        return {}
    root = fromstring(archive.read(name))
    scheme = root.find(".//" + A + "clrScheme")
    colors = {}
    for entry in scheme if scheme is not None else []:
        value = next(iter(entry), None)
        if value is not None:
            colors[entry.tag.split("}")[-1]] = safe_color("#" + (value.get("val") if value.tag == A+"srgbClr" else value.get("lastClr", "")))
    for alias, name in {"dark1":"dk1", "light1":"lt1", "dark2":"dk2", "light2":"lt2", "text1":"dk1", "background1":"lt1"}.items():
        colors[alias] = colors.get(name)
    return colors


def _word_props(properties, theme):
    result = {}
    if properties is None:
        return result
    color = properties.find(W+"color")
    if color is not None:
        raw = color.get(W+"val", "auto")
        value = theme.get(color.get(W+"themeColor")) or safe_color("#"+raw)
        if value and theme.get(color.get(W+"themeColor")):
            channels = [int(value[i:i+2],16)/255 for i in (1,3,5)]
            hue,luminance,saturation=colorsys.rgb_to_hls(*channels)
            tint, shade = color.get(W+"themeTint"), color.get(W+"themeShade")
            if tint:
                coefficient=int(tint,16)/255
                luminance=luminance*coefficient+(1-coefficient)
            elif shade:
                luminance*=int(shade,16)/255
            channels=[round(c*255) for c in colorsys.hls_to_rgb(hue,luminance,saturation)]
            value = "#" + "".join(f"{c:02X}" for c in channels)
        result["color"] = value
    for name in ("strike", "dstrike"):
        strike = properties.find(W+name)
        if strike is not None:
            result["strike"] = strike.get(W+"val", "true").lower() not in {"0","false","off"}
    return result


def prepare_docx(source: Path, markers: FormattingMarkers) -> BytesIO:
    output = BytesIO()
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as target:
        theme = _theme(archive)
        styles_root = fromstring(archive.read("word/styles.xml")) if "word/styles.xml" in archive.namelist() else None
        styles = {style.get(W+"styleId"):style for style in styles_root.findall(W+"style")} if styles_root is not None else {}
        defaults = _word_props(styles_root.find(W+"docDefaults/"+W+"rPrDefault/"+W+"rPr"),theme) if styles_root is not None else {}
        normal = next((key for key,value in styles.items() if value.get(W+"type")=="paragraph" and value.get(W+"default")=="1"), "Normal")
        def inherited(style_id, seen=None):
            seen = set() if seen is None else seen
            if style_id in seen or style_id not in styles:
                return {}
            seen.add(style_id)
            style=styles[style_id]
            base=style.find(W+"basedOn")
            props=inherited(base.get(W+"val"),seen) if base is not None else {}
            props.update(_word_props(style.find(W+"rPr"),theme))
            return props
        for item in archive.infolist():
            data = archive.read(item)
            if re.fullmatch(r"word/(document|footnotes|endnotes|header\d+|footer\d+)\.xml",item.filename):
                root = fromstring(data)
                for paragraph in root.iter(W+"p"):
                    paragraph_props = dict(defaults)
                    pstyle=paragraph.find(W+"pPr/"+W+"pStyle")
                    paragraph_props.update(inherited(pstyle.get(W+"val") if pstyle is not None else normal))
                    for run in paragraph.iter(W+"r"):
                        properties=run.find(W+"rPr")
                        props=dict(paragraph_props)
                        rstyle=properties.find(W+"rStyle") if properties is not None else None
                        if rstyle is not None:
                            props.update(inherited(rstyle.get(W+"val")))
                        props.update(_word_props(properties,theme))
                        texts=list(run.iter(W+"t"))
                        if texts and any((text.text or "").strip() for text in texts) and (props.get("color") or props.get("strike")):
                            # Put markers outside the run's ordinary text, including multi-node runs.
                            start,end=markers.wrap("X",props.get("color"),props.get("strike",False)).split("X")
                            leading=(texts[0].text or "")[:len(texts[0].text or "")-len((texts[0].text or "").lstrip())]
                            trailing=(texts[-1].text or "")[len((texts[-1].text or "").rstrip()):]
                            texts[0].text=leading+start+(texts[0].text or "").lstrip()
                            texts[-1].text=(texts[-1].text or "").rstrip()+end+trailing
                            if properties is not None:
                                for strike in list(properties):
                                    if strike.tag in {W+"strike", W+"dstrike"}:
                                        properties.remove(strike)
                data=ET.tostring(root,encoding="utf-8",xml_declaration=True)
            elif item.filename == "word/styles.xml":
                root=fromstring(data)
                for parent in root.iter():
                    for child in list(parent):
                        if child.tag in {W+"strike",W+"dstrike"}:
                            parent.remove(child)
                data=ET.tostring(root,encoding="utf-8",xml_declaration=True)
            target.writestr(item,data)
    output.seek(0)
    return output


def prepare_html(source: Path, markers: FormattingMarkers) -> BytesIO:
    from bs4 import BeautifulSoup, NavigableString, Comment
    from charset_normalizer import from_bytes
    decoded=from_bytes(source.read_bytes()).best()
    soup=BeautifulSoup(str(decoded) if decoded is not None else source.read_text(encoding="utf-8",errors="replace"),"html.parser")
    for node in list(soup.find_all(string=True)):
        if not isinstance(node,NavigableString) or isinstance(node,Comment) or not node.strip():
            continue
        parents=list(node.parents)
        if any(parent.name in {"script","style","pre","code"} for parent in parents):
            continue
        color=None
        strike=False
        color_seen=False
        strike_seen=False
        for parent in parents:
            declarations={key.strip().lower():value.strip() for key,value in re.findall(r"([\w-]+)\s*:\s*([^;]+)",parent.get("style", ""))}
            value=declarations.get("color") or (parent.get("color") if parent.name == "font" else None)
            if value and not color_seen:
                color=safe_color(value);color_seen=True
            decoration=declarations.get("text-decoration",declarations.get("text-decoration-line",""))
            if "line-through" in decoration:
                strike=True
            if parent.name in {"s","del","strike"}:
                strike_seen=True
        # Native semantic strike tags are already handled by the engine.
        wrapped=markers.wrap(str(node),color,strike and not strike_seen)
        if wrapped != str(node):
            node.replace_with(wrapped)
    return BytesIO(str(soup).encode("utf-8"))


def prepare_pptx(source: Path, markers: FormattingMarkers) -> BytesIO:
    output=BytesIO()
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as target:
        theme=_theme(archive)
        for item in archive.infolist():
            data=archive.read(item)
            if re.fullmatch(r"ppt/(slides/slide\d+|notesSlides/notesSlide\d+)\.xml",item.filename):
                root=fromstring(data)
                for paragraph in root.iter(A+"p"):
                    default=paragraph.find(A+"pPr/"+A+"defRPr")
                    for run in paragraph.findall(A+"r"):
                        properties=run.find(A+"rPr")
                        color=None
                        strike=False
                        for prop in (default,properties):
                            if prop is None:continue
                            fill=prop.find(A+"solidFill")
                            if fill is not None:
                                rgb=fill.find(A+"srgbClr")
                                scheme=fill.find(A+"schemeClr")
                                color=safe_color("#"+rgb.get("val","")) if rgb is not None else theme.get(scheme.get("val")) if scheme is not None else None
                            if "strike" in prop.attrib:
                                strike=prop.get("strike") not in {"noStrike","0","false"}
                        text=run.find(A+"t")
                        if text is not None:
                            text.text=markers.wrap(text.text or "",color,strike)
                data=ET.tostring(root,encoding="utf-8",xml_declaration=True)
            target.writestr(item,data)
    output.seek(0)
    return output


def convert_xlsx(source: Path) -> str:
    """Keep cell/rich-run font colors and strikes in ordinary XLSX tables."""
    from openpyxl import load_workbook
    from openpyxl.styles.colors import COLOR_INDEX
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from html import escape
    book=load_workbook(source,data_only=True,rich_text=True)
    theme=[]
    if book.loaded_theme:
        root=fromstring(book.loaded_theme)
        scheme=root.find(".//"+A+"clrScheme")
        mapping={entry.tag.split("}")[-1]:(next(iter(entry)).get("lastClr","") if next(iter(entry)).tag==A+"sysClr" else next(iter(entry)).get("val","")) for entry in scheme} if scheme is not None else {}
        theme=[mapping.get(name,"") for name in ("lt1","dk1","lt2","dk2","accent1","accent2","accent3","accent4","accent5","accent6","hlink","folHlink")]
    def color_of(font):
        color=font.color
        if color is None:return None
        raw=None
        if color.type=="rgb":raw=color.rgb[-6:]
        elif color.type=="indexed" and color.indexed < len(COLOR_INDEX):raw=COLOR_INDEX[color.indexed][-6:]
        elif color.type=="theme" and color.theme < len(theme):raw=theme[color.theme]
        value=safe_color("#"+raw) if raw else None
        if value and color.tint:
            channels=[int(value[i:i+2],16) for i in (1,3,5)]
            channels=[round(c*(1+color.tint) if color.tint<0 else c+(255-c)*color.tint) for c in channels]
            value="#"+"".join(f"{c:02X}" for c in channels)
        return value
    def render(value,font):
        if value is None:return ""
        text=escape(str(value),quote=False)
        text=re.sub(r"([\\`*_~\[\]|])",r"\\\1",text).replace("\r\n","\n").replace("\n","<br>")
        if font.b:text=f"**{text}**"
        if font.i:text=f"*{text}*"
        color=color_of(font)
        if font.strike:text=f"<del>{text}</del>" if color else f"~~{text}~~"
        return f'<span style="color: {color}">{text}</span>' if color else text
    sections=[]
    try:
        for sheet in book:
            rows=[]
            for row in sheet.iter_rows():
                values=[]
                for cell in row:
                    if isinstance(cell.value,CellRichText):
                        values.append("".join(render(part.text,part.font) if isinstance(part,TextBlock) else render(part,cell.font) for part in cell.value))
                    else:values.append(render(cell.value,cell.font))
                rows.append(values)
            while rows and not any(rows[-1]):rows.pop()
            while rows and not any(rows[0]):rows.pop(0)
            if not rows:continue
            width=max((index+1 for row in rows for index,value in enumerate(row) if value),default=0)
            rows=[row[:width] for row in rows]
            table=["| "+" | ".join(rows[0])+" |", "| "+" | ".join(["---"]*width)+" |"]
            table.extend("| "+" | ".join(row)+" |" for row in rows[1:])
            sections.append("## "+sheet.title+"\n\n"+"\n".join(table))
    finally:book.close()
    return "\n\n".join(sections)


def convert_rich_document(engine, source: Path) -> str:
    from markitdown import StreamInfo
    markers=FormattingMarkers()
    extension=source.suffix.lower()
    stream=prepare_docx(source,markers) if extension==".docx" else prepare_pptx(source,markers) if extension==".pptx" else prepare_html(source,markers)
    info=StreamInfo(extension=extension if extension in {".docx",".pptx"} else ".html",charset=None if extension in {".docx",".pptx"} else "utf-8")
    result=engine.convert_stream(stream,stream_info=info)
    return markers.restore(result.text_content)
