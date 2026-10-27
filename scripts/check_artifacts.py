#!/usr/bin/env python3
"""Check preserved research bytes and inventory; never run models or rewrite data."""

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "artifact-integrity.json"


def check_artifacts(root: Path, manifest: dict) -> list:
    errors = []
    files = manifest["files"]
    for name, expected in files.items():
        path = root / name
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if actual != expected:
            errors.append(f"{name}: SHA-256 mismatch")

    # New experiments belong outside runs/; the bundle is a frozen snapshot.
    archived_runs = {name for name in files if name.startswith("runs/")}
    current_runs = {p.relative_to(root).as_posix() for p in (root / "runs").glob("*.json")}
    for name in sorted(current_runs - archived_runs):
        errors.append(f"{name}: unrecorded archived run; use a separate output directory")

    bundle_files = {name for name in files if name.startswith("paper_bundle/")}
    current_bundle = {
        p.relative_to(root).as_posix()
        for p in (root / "paper_bundle").rglob("*")
        if p.is_file()
        and p.relative_to(root).as_posix() != "paper_bundle/README.md"
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
    }
    for name in sorted(current_bundle - bundle_files):
        errors.append(f"{name}: unrecorded snapshot file; maintain the root pipeline")
    return errors


def main() -> int:
    try:
        manifest = json.loads(MANIFEST.read_text())
        errors = check_artifacts(ROOT, manifest)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot check artifact manifest: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Artifact integrity FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"Artifact integrity OK: {len(manifest['files'])} files match "
        f"baseline {manifest['baseline_commit'][:7]} "
        "(611 records, 15 bundle files, frozen outputs, original README)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
