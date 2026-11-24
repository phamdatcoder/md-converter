import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"markitdown-main/packages/markitdown/src"))


@unittest.skipUnless(importlib.util.find_spec("mammoth") and importlib.util.find_spec("PIL"),"Requires document dependencies")
class FormattingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from desktop.conversion import MarkItDownBackend
        cls.backend=MarkItDownBackend()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def word(self,paragraphs,styles=""):
        ns="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        document=f'<w:document xmlns:w="{ns}"><w:body>{paragraphs}</w:body></w:document>'
        path=self.root/"Định dạng.docx"
        fixture=ROOT/"markitdown-main/packages/markitdown/tests/test_files/test.docx"
        with zipfile.ZipFile(fixture) as original,zipfile.ZipFile(path,"w") as target:
            for item in original.infolist():
                data=original.read(item)
                if item.filename=="word/document.xml":data=document.encode()
                if item.filename=="word/styles.xml" and styles:data=f'<w:styles xmlns:w="{ns}">{styles}</w:styles>'.encode()
                target.writestr(item,data)
        before=path.read_bytes()
        result=self.backend.convert(path)
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn("MDFMT",result)
        return result

    def test_word_color_strike_and_combination(self):
        result=self.word('''<w:p>
        <w:r><w:rPr><w:color w:val="FF0000"/></w:rPr><w:t>Chữ đỏ</w:t></w:r>
        <w:r><w:rPr><w:strike/></w:rPr><w:t>Gạch bỏ</w:t></w:r>
        <w:r><w:rPr><w:color w:val="008000"/><w:dstrike/></w:rPr><w:t>Cả hai</w:t></w:r>
        </w:p>''')
        self.assertIn('<span style="color: #FF0000">Chữ đỏ</span>',result)
        self.assertIn('~~Gạch bỏ~~',result)
        self.assertIn('<span style="color: #008000"><del>Cả hai</del></span>',result)

    def test_word_style_inheritance_and_explicit_strike_off(self):
        result=self.word('''<w:p><w:pPr><w:pStyle w:val="Parent"/></w:pPr>
        <w:r><w:t>Kế thừa</w:t></w:r>
        <w:r><w:rPr><w:color w:val="auto"/><w:strike w:val="0"/></w:rPr><w:t>Chữ thường</w:t></w:r></w:p>''',
        '''<w:style w:type="paragraph" w:styleId="Parent"><w:name w:val="Parent"/>
        <w:rPr><w:color w:val="0000FF"/><w:strike/></w:rPr></w:style>''')
        self.assertIn('<span style="color: #0000FF"><del>Kế thừa</del></span>',result)
        self.assertIn('Chữ thường',result)
        self.assertNotIn('~~~~',result)
        self.assertNotIn('<del>Chữ thường',result)

    def test_word_multiple_text_nodes_spaces_and_bold(self):
        result=self.word('''<w:p><w:r><w:rPr><w:b/><w:color w:val="FF0000"/></w:rPr>
        <w:t xml:space="preserve">  Xin </w:t><w:t xml:space="preserve">chào  </w:t></w:r></w:p>''')
        self.assertIn('Xin chào',result)
        self.assertIn('**',result)
        self.assertIn('color: #FF0000',result)

    def test_word_theme_tint_uses_hsl_luminance(self):
        from desktop.rich_text import _word_props, W
        from xml.etree.ElementTree import fromstring
        xml='<w:rPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:color w:val="95B3D7" w:themeColor="accent2" w:themeTint="99"/></w:rPr>'
        props=_word_props(fromstring(xml),{"accent2":"#4F81BD"})
        self.assertEqual(props["color"],"#95B3D7")

    def html(self,body):
        path=self.root/"Định dạng.html"
        path.write_text('<meta charset="utf-8">'+body,encoding="utf-8")
        result=self.backend.convert(path)
        self.assertNotIn("MDFMT",result)
        return result

    def test_html_colors_deletion_and_css_line_through(self):
        result=self.html('<p><font color="red">Đỏ</font> <s>Cũ</s> <span style="color:rgb(0,128,0);text-decoration:line-through">Cả hai</span></p>')
        self.assertIn('<span style="color: #FF0000">Đỏ</span>',result)
        self.assertIn('~~Cũ~~',result)
        self.assertIn('<span style="color: #008000"><del>Cả hai</del></span>',result)

    def test_html_headings_tables_and_inheritance_remain(self):
        result=self.html('<h1 style="color:blue">Tiêu đề</h1><div style="color:red"><b>Đậm</b><span style="color:green">Xanh</span></div><table><tr><th>Cột</th></tr><tr><td>Ô</td></tr></table>')
        self.assertIn('# <span style="color: #0000FF">Tiêu đề</span>',result)
        self.assertIn('**<span style="color: #FF0000">Đậm</span>**',result)
        self.assertIn('color: #008000',result)
        self.assertIn('|',result)

    def test_unsafe_color_and_code_not_converted_to_html(self):
        result=self.html('<p style="color:expression(alert(1))">An toàn</p><pre><code style="color:red">print(1)</code></pre>')
        self.assertNotIn('expression',result)
        self.assertNotIn('<span',result)
        self.assertIn('print(1)',result)

    def test_xlsx_cell_and_rich_run_font_styles(self):
        from openpyxl import Workbook
        from openpyxl.styles import Font, Color
        from openpyxl.cell.rich_text import CellRichText, TextBlock
        from openpyxl.cell.text import InlineFont
        book=Workbook();sheet=book.active
        sheet.append(["Cột", "Giá trị"])
        sheet.append(["Chữ đỏ", "Cũ"])
        sheet["A2"].font=Font(color="FF0000",strike=True)
        sheet["B2"].font=Font(strike=True)
        sheet["A3"]=CellRichText("Thường ",TextBlock(InlineFont(color="008000",strike=True),"Xanh"))
        sheet["B3"]="Đen"
        sheet["B3"].font=Font(color=Color(theme=1))
        path=self.root/"Định dạng.xlsx";book.save(path);book.close()
        result=self.backend.convert(path)
        self.assertIn('<span style="color: #FF0000"><del>Chữ đỏ</del></span>',result)
        self.assertIn('~~Cũ~~',result)
        self.assertIn('<span style="color: #008000"><del>Xanh</del></span>',result)
        self.assertIn('<span style="color: #000000">Đen</span>',result)

    def test_powerpoint_run_color_and_strike(self):
        from pptx import Presentation
        from pptx.util import Inches
        from pptx.dml.color import RGBColor
        deck=Presentation();slide=deck.slides.add_slide(deck.slide_layouts[6])
        frame=slide.shapes.add_textbox(Inches(1),Inches(1),Inches(5),Inches(2)).text_frame
        run=frame.paragraphs[0].add_run();run.text="Chữ đỏ bị gạch"
        run.font.color.rgb=RGBColor(255,0,0)
        run._r.get_or_add_rPr().set("strike","sngStrike")
        path=self.root/"Định dạng.pptx";deck.save(path)
        result=self.backend.convert(path)
        self.assertIn('<span style="color: #FF0000"><del>Chữ đỏ bị gạch</del></span>',result)
