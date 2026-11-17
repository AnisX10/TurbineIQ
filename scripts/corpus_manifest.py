"""Validate, fetch and verify the document corpus listed in data/corpus/manifest.json.

    python scripts/corpus_manifest.py validate
    python scripts/corpus_manifest.py fetch [--update]    # download missing files
    python scripts/corpus_manifest.py verify              # check sha256 of local files

Files live in data/corpus/files/ (git-ignored). Only documents marked redistributable may
be committed; everything else is fetched or supplied locally. An entry with an empty
sha256 is filled in by ``fetch --update`` the first time it is downloaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/corpus/manifest.json"
FILES = ROOT / "data/corpus/files"
REQUIRED = ("id", "title", "publisher", "year", "url", "licence", "redistributable", "filename")


def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def validate(manifest: dict) -> list[str]:
    problems: list[str] = []
    seen_ids, seen_files = set(), set()
    for i, doc in enumerate(manifest.get("documents", [])):
        label = doc.get("id", f"#{i}")
        for key in REQUIRED:
            if key not in doc or doc[key] in ("", None):
                problems.append(f"{label}: missing {key}")
        if not str(doc.get("url", "")).startswith("https://"):
            problems.append(f"{label}: url must be https")
        if not isinstance(doc.get("redistributable"), bool):
            problems.append(f"{label}: redistributable must be true or false")
        if Path(str(doc.get("filename", ""))).name != doc.get("filename"):
            problems.append(f"{label}: filename must not contain a path")
        if doc.get("id") in seen_ids or doc.get("filename") in seen_files:
            problems.append(f"{label}: duplicate id or filename")
        seen_ids.add(doc.get("id"))
        seen_files.add(doc.get("filename"))
    return problems


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("validate", "fetch", "verify"))
    parser.add_argument("--update", action="store_true", help="write new sha256 values")
    args = parser.parse_args()
    manifest = load()
    problems = validate(manifest)
    if problems:
        print(*problems, sep="\n", file=sys.stderr)
        return 1
    if args.action == "validate":
        print(f"{len(manifest['documents'])} documents, manifest valid")
        return 0
    FILES.mkdir(parents=True, exist_ok=True)
    status = 0
    for doc in manifest["documents"]:
        path = FILES / doc["filename"]
        if args.action == "fetch" and not path.exists():
            try:
                request = urllib.request.Request(
                    doc["url"], headers={"User-Agent": "turbineiq-corpus"}
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    path.write_bytes(response.read())
            except OSError as exc:
                print(f"{doc['id']}: download failed: {exc}", file=sys.stderr)
                status = 1
                continue
        if not path.exists():
            print(f"{doc['id']}: missing {path.name}", file=sys.stderr)
            status = 1
            continue
        digest = sha256(path)
        if not doc.get("sha256"):
            if args.update:
                doc["sha256"] = digest
                print(f"{doc['id']}: recorded sha256 {digest[:12]}")
            else:
                print(f"{doc['id']}: no sha256 recorded (run fetch --update)", file=sys.stderr)
                status = 1
        elif digest != doc["sha256"]:
            print(f"{doc['id']}: sha256 mismatch", file=sys.stderr)
            status = 1
        else:
            print(f"{doc['id']}: ok")
    if args.update:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
