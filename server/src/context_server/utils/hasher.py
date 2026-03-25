"""SHA-256 file hashing for incremental updates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_file(file_path: str | Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hashes(hashes_path: Path) -> dict[str, str]:
    """Load file hashes from JSON."""
    if not hashes_path.exists():
        return {}
    return json.loads(hashes_path.read_text())


def save_hashes(hashes_path: Path, hashes: dict[str, str]) -> None:
    """Save file hashes to JSON."""
    hashes_path.parent.mkdir(parents=True, exist_ok=True)
    hashes_path.write_text(json.dumps(hashes, indent=2))


def get_changed_files(
    files: list[dict], hashes_path: Path
) -> tuple[list[dict], list[str], dict[str, str]]:
    """Compare current files against stored hashes.

    Returns:
        - changed_files: files that are new or modified
        - deleted_paths: relative paths of files that were deleted
        - new_hashes: updated hash dict for all current files
    """
    old_hashes = load_hashes(hashes_path)
    new_hashes: dict[str, str] = {}
    changed: list[dict] = []

    current_paths = set()
    for file_info in files:
        rel = file_info["relative_path"]
        current_paths.add(rel)
        file_hash = hash_file(file_info["path"])
        new_hashes[rel] = file_hash
        if old_hashes.get(rel) != file_hash:
            changed.append(file_info)

    deleted = [p for p in old_hashes if p not in current_paths]
    return changed, deleted, new_hashes
