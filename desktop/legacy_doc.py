"""Extract the main text of unencrypted Word 97–2003 DOC files.

Follows MS-DOC 2.4.1 (Retrieving Text). This intentionally extracts text,
paragraphs and table cell boundaries, not Word's layout, images or styles.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path


def _read(fmt: str, data: bytes, offset: int) -> int:
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(data):
        raise ValueError("File DOC bị hỏng hoặc thiếu dữ liệu.")
    return struct.unpack_from(fmt, data, offset)[0]


def extract_word_text(word: bytes, table: bytes) -> str:
    """Decode the DOC piece table, limiting output to the main document story."""
    if _read("<H", word, 0) != 0xA5EC or _read("<H", word, 2) < 0x00C1:
        raise ValueError("Chỉ hỗ trợ DOC Word 97–2003. Hãy lưu file cũ hơn thành DOCX.")
    flags = _read("<H", word, 10)
    if flags & 0x8100:
        raise ValueError("File DOC có mật khẩu. Hãy bỏ mật khẩu trước khi chuyển đổi.")
    # FIB: FibBase (32), csw + FibRgW, cslw + FibRgLw, cbRgFcLcb.
    csw = _read("<H", word, 32)
    lw_start = 34 + csw * 2
    cslw = _read("<H", word, lw_start)
    if cslw < 4:
        raise ValueError("Header DOC không hợp lệ.")
    ccp_text = _read("<I", word, lw_start + 2 + 3 * 4)
    pairs_start = lw_start + 2 + cslw * 4
    if _read("<H", word, pairs_start) < 34:
        raise ValueError("DOC thiếu bảng vị trí văn bản.")
    # fcClx/lcbClx are pair 33 of FibRgFcLcb97.
    fc_clx = _read("<I", word, pairs_start + 2 + 33 * 8)
    lcb_clx = _read("<I", word, pairs_start + 2 + 33 * 8 + 4)
    if fc_clx + lcb_clx > len(table):
        raise ValueError("Bảng văn bản DOC bị hỏng.")
    clx = table[fc_clx:fc_clx + lcb_clx]
    position = 0
    while position < len(clx) and clx[position] == 1:
        length = _read("<H", clx, position + 1)
        position += 3 + length
    if position >= len(clx) or clx[position] != 2:
        raise ValueError("Không tìm thấy bảng văn bản trong DOC.")
    length = _read("<I", clx, position + 1)
    plc = clx[position + 5:position + 5 + length]
    if length < 4 or (length - 4) % 12 or len(plc) != length:
        raise ValueError("Bảng văn bản DOC không hợp lệ.")
    count = (length - 4) // 12
    descriptors = (count + 1) * 4
    chunks: list[str] = []
    previous_cp = 0
    for index in range(count):
        start = _read("<I", plc, index * 4)
        end = _read("<I", plc, (index + 1) * 4)
        if start != previous_cp or end < start:
            raise ValueError("Thứ tự văn bản DOC không hợp lệ.")
        previous_cp = end
        if start >= ccp_text:
            break
        characters = min(end, ccp_text) - start
        encoded_fc = _read("<I", plc, descriptors + index * 8 + 2)
        compressed = bool(encoded_fc & 0x40000000)
        offset = encoded_fc & 0x3FFFFFFF
        if compressed:
            offset //= 2
        byte_count = characters * (1 if compressed else 2)
        if offset + byte_count > len(word):
            raise ValueError("Nội dung DOC bị cắt ngắn.")
        raw = word[offset:offset + byte_count]
        chunks.append(raw.decode("cp1252" if compressed else "utf-16-le", errors="replace"))
    if previous_cp < ccp_text:
        raise ValueError("Bảng văn bản DOC không chứa đủ nội dung.")
    text = "".join(chunks)
    # Word fields: discard instructions, retain their displayed results.
    text = re.sub(r"\x13[^\x13\x14\x15]*\x14([^\x13\x15]*)\x15", r"\1", text)
    text = re.sub(r"\x13[^\x13\x15]*\x15", "", text)
    text = text.replace("\r\x07", "\t").replace("\x07", "\t")
    text = text.replace("\r", "\n\n").replace("\x0b", "\n").replace("\x0c", "\n\n")
    text = re.sub(r"[\x00-\x08\x0e-\x1f]", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def convert_doc(source: Path) -> str:
    import olefile

    if not olefile.isOleFile(str(source)):
        # Some old word processors save RTF under a .doc extension.
        data = source.read_bytes()
        if data.lstrip().startswith(b"{\\rtf"):
            from striprtf.striprtf import rtf_to_text

            return rtf_to_text(data.decode("latin-1"), errors="replace")
        raise ValueError("File không phải DOC Word 97–2003 hợp lệ. Hãy lưu lại thành DOCX.")
    with olefile.OleFileIO(str(source)) as document:
        if not document.exists("WordDocument"):
            raise ValueError("File DOC thiếu luồng WordDocument.")
        word = document.openstream("WordDocument").read()
        flags = _read("<H", word, 10)
        if flags & 0x8100:
            raise ValueError("File DOC có mật khẩu. Hãy bỏ mật khẩu trước khi chuyển đổi.")
        table_name = "1Table" if flags & 0x0200 else "0Table"
        if not document.exists(table_name):
            raise ValueError("File DOC thiếu bảng văn bản.")
        return extract_word_text(word, document.openstream(table_name).read())
