"""Gitignore-aware directory walker for project scanning."""

from __future__ import annotations

import os
from pathlib import Path

import pathspec


DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "venv/",
    ".env/",
    "dist/",
    "build/",
    ".next/",
    ".nuxt/",
    "target/",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.class",
    "*.o",
    "*.exe",
    ".DS_Store",
    "Thumbs.db",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".claude/",
]

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
}


def load_gitignore(project_root: Path) -> pathspec.PathSpec:
    """Load .gitignore patterns from the project root."""
    patterns = list(DEFAULT_IGNORE_PATTERNS)

    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        patterns.extend(gitignore_path.read_text().splitlines())

    context_ignore = project_root / ".code-contextignore"
    if context_ignore.exists():
        patterns.extend(context_ignore.read_text().splitlines())

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def walk_project(
    project_root: Path,
    max_file_size_kb: int = 100,
) -> list[dict]:
    """Walk the project tree and return file metadata.

    Returns a list of dicts with keys: path, relative_path, language, size_bytes.
    """
    spec = load_gitignore(project_root)
    files = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = os.path.relpath(dirpath, project_root)
        if rel_dir == ".":
            rel_dir = ""

        # Filter out ignored directories in-place
        dirnames[:] = [
            d
            for d in dirnames
            if not spec.match_file(os.path.join(rel_dir, d) + "/")
        ]

        for filename in filenames:
            rel_path = os.path.join(rel_dir, filename) if rel_dir else filename
            if spec.match_file(rel_path):
                continue

            full_path = os.path.join(dirpath, filename)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue

            if size > max_file_size_kb * 1024:
                continue

            ext = os.path.splitext(filename)[1]
            language = SUPPORTED_EXTENSIONS.get(ext)
            if language is None:
                continue

            files.append(
                {
                    "path": full_path,
                    "relative_path": rel_path,
                    "language": language,
                    "size_bytes": size,
                }
            )

    return files


def generate_tree(project_root: Path, max_depth: int = 4) -> str:
    """Generate a compact tree representation of the project."""
    spec = load_gitignore(project_root)
    lines: list[str] = []

    def _walk(dir_path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return

        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return

        # Filter entries
        filtered = []
        for entry in entries:
            rel = entry.relative_to(project_root)
            rel_str = str(rel) + ("/" if entry.is_dir() else "")
            if not spec.match_file(rel_str):
                filtered.append(entry)

        for i, entry in enumerate(filtered):
            is_last = i == len(filtered) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    lines.append(project_root.name + "/")
    _walk(project_root, "", 1)
    return "\n".join(lines)
