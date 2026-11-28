"""Convert local PDFs and audit page coverage; never upload or alter inputs."""

import argparse
from collections import Counter
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop.pdf_layout import extract_pdf


def characters(text):
    text = unicodedata.normalize("NFC", unescape(text))
    return Counter(char for char in text if char.isalnum())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "pdf_test")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = sorted(args.input.glob("*.pdf"))
    if not sources:
        parser.error("No PDFs found in the input folder")
    args.output.mkdir(parents=True, exist_ok=False)
    import pdfplumber

    documents = []
    for source in sources:
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        converted = extract_pdf(source)
        target = args.output / (source.stem + ".md")
        target.write_text(converted.markdown + "\n", encoding="utf-8")
        pages = re.split(r"<!-- PDF page: \d+ -->", converted.markdown)[1:]
        with pdfplumber.open(source) as document:
            for number, page in enumerate(document.pages):
                source_text = "".join(char["text"] for char in page.chars)
                # Omit image labels and base64 definitions from the comparison.
                result_text = pages[number].split("<!-- Embedded original images;")[0]
                result_text = re.sub(r"!\[[^\n]*\]\[pdf-image-[^\]]+\]", "", result_text)
                missing = characters(source_text) - characters(result_text)
                converted.report["pages"][number]["missing_alphanumeric_characters"] = dict(missing)
                converted.report["pages"][number]["source_alphanumeric_characters"] = sum(characters(source_text).values())
                page.close()
        after = hashlib.sha256(source.read_bytes()).hexdigest()
        if before != after:
            raise RuntimeError("Source PDF changed: " + source.name)
        converted.report["source_sha256"] = before
        converted.report["output"] = target.name
        converted.report["source_unchanged"] = True
        items = converted.report["pages"]
        converted.report["summary"] = {
            "pages": len(items),
            "headings": sum(len(item["headings"]) for item in items),
            "headings_from_bookmarks": sum(h["method"] == "bookmark" for item in items for h in item["headings"]),
            "code_blocks": sum(item["code_blocks"] for item in items),
            "tables": sum(item["tables"] for item in items),
            "images_preserved": sum(item["images_preserved"] for item in items),
            "headers": sum(len(item["headers"]) for item in items),
            "footers": sum(len(item["footers"]) for item in items),
            "pages_needing_ocr": [item["page"] for item in items if "needs_ocr" in item["warnings"]],
            "pages_with_missing_characters": [item["page"] for item in items if item["missing_alphanumeric_characters"]],
        }
        documents.append(converted.report)
        print(json.dumps({"file": source.name, **converted.report["summary"]}, ensure_ascii=True), flush=True)
    report = {"documents": documents,
              "audit_limit": "Per-page alphanumeric character counts detect some omissions, not reading order, OCR accuracy, or semantic completeness. Embedded images are preserved, not transcribed."}
    (args.output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(any(doc["summary"]["pages_with_missing_characters"] for doc in documents))


if __name__ == "__main__":
    raise SystemExit(main())
