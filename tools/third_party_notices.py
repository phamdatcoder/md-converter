"""Collect installed dependency licenses for embedding in the executable."""

from importlib.metadata import distributions
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parts = [
    "MD Converter — third-party notices\n",
    "MarkItDown (Microsoft):\n" + (root / "markitdown-main/LICENSE").read_text(encoding="utf-8"),
]
for dist in sorted(distributions(), key=lambda item: item.metadata.get("Name", "").lower()):
    parts.append(f"\n{'=' * 72}\n{dist.metadata.get('Name', '')} {dist.version}\n")
    parts.append("License: " + str(dist.metadata.get("License-Expression") or dist.metadata.get("License", "See license files")))
    for file in dist.files or []:
        if "license" in file.name.lower() or "notice" in file.name.lower() or "copying" in file.name.lower():
            try:
                path = Path(dist.locate_file(file))
                if path.is_file():
                    parts.append(f"\n{file}:\n" + path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
target = root / ".build-tools/THIRD_PARTY_NOTICES.txt"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("\n".join(parts), encoding="utf-8")
