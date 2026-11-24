"""Verify the EXE contains the exact images from the approved comic ICO."""

from collections import Counter
from pathlib import Path
import struct
import sys
import pefile

root = Path(__file__).resolve().parents[1]
executable = Path(sys.argv[1])
source = (root / "desktop/assets/md-converter.ico").read_bytes()
reserved, kind, count = struct.unpack_from("<HHH", source)
assert reserved == 0 and kind == 1 and count >= 7, "Incomplete source icon"
expected = []
for index in range(count):
    entry = struct.unpack_from("<BBBBHHII", source, 6 + index * 16)
    length, offset = entry[-2:]
    expected.append(source[offset:offset+length])
with pefile.PE(str(executable)) as pe:
    resources = {entry.id: entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
    groups = resources[14].directory.entries
    assert len(groups) == 1, "Unexpected EXE icon groups"
    group_data = groups[0].directory.entries[0].data.struct
    group = pe.get_data(group_data.OffsetToData, group_data.Size)
    icon_resources = {entry.id: entry for entry in resources[3].directory.entries}
    actual = []
    for index in range(struct.unpack_from("<H", group, 4)[0]):
        icon_id = struct.unpack_from("<H", group, 6 + index * 14 + 12)[0]
        data = icon_resources[icon_id].directory.entries[0].data.struct
        actual.append(pe.get_data(data.OffsetToData, data.Size))
    assert Counter(actual) == Counter(expected), "EXE icon differs from the comic ICO"
print(f"EXE comic icon verified: {len(actual)} embedded images match the original ICO")
