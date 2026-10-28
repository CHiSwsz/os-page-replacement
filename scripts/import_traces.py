#!/usr/bin/env python3
"""Import the four assigned traces, preserving their exact original bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

DATASETS = [("qsort", "sort1.txt", 524, 192), ("lu", "lu.txt", 41832, 531),
            ("mm16", "mm16.txt", 9075, 515), ("mm32", "mm32.txt", 67235, 1667)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args()
    manifest = {"source": "Course-provided TraceSet1.zip", "source_archive_sha256":
                hashlib.sha256(args.archive.read_bytes()).hexdigest(), "datasets": []}
    validated = []
    with zipfile.ZipFile(args.archive) as archive:
        for name, filename, references, unique in DATASETS:
            raw = archive.read("TraceSet1/" + filename)
            lines = [line.strip() for line in raw.decode("ascii").splitlines() if line.strip()]
            if not all(re.fullmatch(r"[0-9a-fA-F]{1,16}", line) for line in lines):
                raise ValueError(f"Malformed page ID in {filename}")
            pages = [int(line, 16) for line in lines]
            if len(pages) != references or len(set(pages)) != unique:
                raise ValueError(f"Unexpected dataset size: {filename}")
            manifest["datasets"].append({"name": name, "file": filename, "references": references,
                                         "unique_pages": unique, "sha256": hashlib.sha256(raw).hexdigest()})
            validated.append((filename, raw))
    args.out.mkdir(parents=True, exist_ok=True)
    for filename, raw in validated:
        (args.out / filename).write_bytes(raw)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Imported and validated four course traces.")


if __name__ == "__main__":
    main()
