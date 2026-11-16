"""Tamper check for the files the advisor treats as ground truth.

The playbook decides which limits a brief may cite, so a changed playbook
changes what the verifier accepts. docs/policies/playbook_manifest.json
records the SHA-256 of each protected file. verify_manifest() recomputes the
hashes before a run, and a mismatch holds the run for a person.

A deliberate playbook change needs a deliberate manifest update, reviewed
like any other change:
    python3 -m src.guardrails.integrity            checks and prints the hashes
    python3 -m src.guardrails.integrity --update   records the current hashes
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = PROJECT_ROOT / "docs" / "policies" / "playbook_manifest.json"
PROTECTED_FILES = ("docs/policies/compensation_governance_playbook.md",)


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    mismatches: tuple[str, ...]
    hashes: dict[str, str]


def file_sha256(path: Path | str) -> str:
    """SHA-256 of a file with Windows line endings normalized, so a checkout setting cannot change it."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def current_hashes(root: Path = PROJECT_ROOT, files: tuple[str, ...] = PROTECTED_FILES) -> dict[str, str]:
    return {rel: file_sha256(root / rel) for rel in files}


def verify_manifest(root: Path = PROJECT_ROOT, manifest_path: Path | None = None) -> IntegrityResult:
    """Compares each protected file with the hash the manifest recorded."""
    manifest_path = manifest_path or (root / "docs" / "policies" / "playbook_manifest.json")
    if not manifest_path.exists():
        return IntegrityResult(False, (f"manifest missing: {manifest_path.name}",), {})
    recorded = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})
    hashes: dict[str, str] = {}
    mismatches: list[str] = []
    for rel, want in recorded.items():
        path = root / rel
        if not path.exists():
            mismatches.append(f"{rel}: file missing")
            continue
        hashes[rel] = file_sha256(path)
        if hashes[rel] != want:
            mismatches.append(f"{rel}: hash {hashes[rel][:12]} differs from the recorded {want[:12]}")
    for rel in PROTECTED_FILES:
        if rel not in recorded:
            mismatches.append(f"{rel}: not listed in the manifest")
    return IntegrityResult(not mismatches, tuple(mismatches), hashes)


def write_manifest(root: Path = PROJECT_ROOT, manifest_path: Path | None = None) -> dict[str, str]:
    manifest_path = manifest_path or (root / "docs" / "policies" / "playbook_manifest.json")
    hashes = current_hashes(root)
    body = {
        "about": "SHA-256 of each file the advisor treats as ground truth. Update with "
        "python3 -m src.guardrails.integrity --update after a reviewed change.",
        "files": hashes,
    }
    manifest_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return hashes


if __name__ == "__main__":
    if "--update" in sys.argv[1:]:
        for rel, digest in write_manifest().items():
            print(f"recorded {digest}  {rel}")
    else:
        result = verify_manifest()
        for rel, digest in result.hashes.items():
            print(f"{digest}  {rel}")
        print("INTEGRITY OK" if result.ok else "INTEGRITY MISMATCH: " + "; ".join(result.mismatches))
        sys.exit(0 if result.ok else 1)
