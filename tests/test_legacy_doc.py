import struct
import unittest

from desktop.legacy_doc import extract_word_text


def document(pieces, *, main_length=None):
    """Construct FIB and piece table as defined by MS-DOC, with mixed encodings."""
    word = bytearray(2048)
    struct.pack_into("<H", word, 0, 0xA5EC)
    struct.pack_into("<H", word, 2, 0x00C1)
    struct.pack_into("<H", word, 32, 14)  # csw
    struct.pack_into("<H", word, 62, 22)  # cslw
    struct.pack_into("<H", word, 152, 93)  # cbRgFcLcb
    cp = 0
    positions = [0]
    descriptors = []
    offset = 1024
    for text, compressed in pieces:
        raw = text.encode("cp1252" if compressed else "utf-16-le")
        word[offset:offset + len(raw)] = raw
        fc = (offset * 2) | 0x40000000 if compressed else offset
        descriptors.append(struct.pack("<HIH", 0, fc, 0))
        cp += len(text.encode("utf-16-le")) // 2
        positions.append(cp)
        offset += len(raw) + 8
    struct.pack_into("<I", word, 76, main_length if main_length is not None else cp)
    plc = struct.pack("<" + "I" * len(positions), *positions) + b"".join(descriptors)
    clx = b"\x02" + struct.pack("<I", len(plc)) + plc
    struct.pack_into("<II", word, 154 + 33 * 8, 0, len(clx))
    return word, clx


class LegacyDocTests(unittest.TestCase):
    def test_mixed_unicode_compressed_pieces_and_paragraphs(self):
        word, table = document([("Heading\r", True), ("Tiếng Việt: Nguyễn Thị Phương Thảo.\r", False)])
        self.assertEqual(extract_word_text(word, table), "Heading\n\nTiếng Việt: Nguyễn Thị Phương Thảo.")

    def test_main_story_excludes_footnotes_and_other_stories(self):
        word, table = document([("Main\r", True), ("Footnote", True)], main_length=5)
        self.assertEqual(extract_word_text(word, table), "Main")

    def test_field_instructions_removed_but_display_text_retained(self):
        word, table = document([('See \x13 HYPERLINK "https://example.org" \x14Example\x15\r', True)])
        self.assertEqual(extract_word_text(word, table), "See Example")

    def test_property_runs_before_piece_table(self):
        word, table = document([("Text\r", True)])
        table = b"\x01\x02\x00AB" + table
        struct.pack_into("<I", word, 154 + 33 * 8 + 4, len(table))
        self.assertEqual(extract_word_text(word, table), "Text")

    def test_encrypted_doc_fails_with_clear_error(self):
        word, table = document([("Secret", True)])
        struct.pack_into("<H", word, 10, 0x0100)
        with self.assertRaisesRegex(ValueError, "mật khẩu"):
            extract_word_text(word, table)

    def test_truncated_piece_table_is_rejected(self):
        word, table = document([("Text", True)])
        with self.assertRaises(ValueError):
            extract_word_text(word, table[:-1])

    def test_invalid_signature_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_word_text(b"bad", b"")

    def test_missing_text_is_rejected(self):
        word, table = document([("Text", True)], main_length=100)
        with self.assertRaises(ValueError):
            extract_word_text(word, table)


if __name__ == "__main__":
    unittest.main()
