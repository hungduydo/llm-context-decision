"""SQLite graph storage for code dependency tracking."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from dataclasses import dataclass

from .parser import CodeNode, CodeEdge


class CodeGraph:
    """SQLite-backed code dependency graph."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                signature TEXT
            );

            CREATE TABLE IF NOT EXISTS edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id, kind)
            );

            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                language TEXT,
                last_parsed TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
            """
        )
        self.conn.commit()

    def upsert_nodes(self, nodes: list[CodeNode]) -> None:
        """Insert or update nodes."""
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO nodes (id, file_path, name, kind, start_line, end_line, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (n.id, n.file_path, n.name, n.kind, n.start_line, n.end_line, n.signature)
                for n in nodes
            ],
        )
        self.conn.commit()

    def upsert_edges(self, edges: list[CodeEdge]) -> None:
        """Insert or update edges."""
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO edges (source_id, target_id, kind)
            VALUES (?, ?, ?)
            """,
            [(e.source_id, e.target_id, e.kind) for e in edges],
        )
        self.conn.commit()

    def upsert_file(self, path: str, sha256: str, language: str) -> None:
        """Record a parsed file."""
        from datetime import datetime, timezone

        self.conn.execute(
            """
            INSERT OR REPLACE INTO files (path, sha256, language, last_parsed)
            VALUES (?, ?, ?, ?)
            """,
            (path, sha256, language, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def remove_file(self, file_path: str) -> None:
        """Remove all nodes/edges for a file."""
        # Get node IDs for this file
        node_ids = [
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM nodes WHERE file_path = ?", (file_path,)
            )
        ]
        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            self.conn.execute(
                f"DELETE FROM edges WHERE source_id IN ({placeholders})", node_ids
            )
            self.conn.execute(
                f"DELETE FROM edges WHERE target_id IN ({placeholders})", node_ids
            )
            self.conn.execute(
                f"DELETE FROM nodes WHERE file_path = ?", (file_path,)
            )
        self.conn.execute("DELETE FROM files WHERE path = ?", (file_path,))
        self.conn.commit()

    def resolve_edges(self) -> int:
        """Resolve wildcard target IDs (e.g., '?::name') to actual node IDs.

        Returns the number of edges resolved.
        """
        # Find all unresolved edges (target starts with '?::')
        unresolved = self.conn.execute(
            "SELECT rowid, source_id, target_id, kind FROM edges WHERE target_id LIKE '?::%'"
        ).fetchall()

        resolved_count = 0
        to_delete = []
        to_insert = []

        for row in unresolved:
            target_name = row["target_id"][3:]  # Remove '?::'

            # For imports, try to match against module nodes
            if row["kind"] == "imports":
                candidates = self.conn.execute(
                    "SELECT id FROM nodes WHERE kind = 'module' AND file_path LIKE ?",
                    (f"%{target_name.replace('.', '/')}%",),
                ).fetchall()
            else:
                # For calls/inherits/tests, match by name
                candidates = self.conn.execute(
                    "SELECT id FROM nodes WHERE name = ? OR name LIKE ?",
                    (target_name, f"%.{target_name}"),
                ).fetchall()

            if candidates:
                to_delete.append(row["rowid"])
                for candidate in candidates:
                    to_insert.append(
                        (row["source_id"], candidate["id"], row["kind"])
                    )
                    resolved_count += 1

        if to_delete:
            placeholders = ",".join("?" * len(to_delete))
            self.conn.execute(
                f"DELETE FROM edges WHERE rowid IN ({placeholders})", to_delete
            )
        for source_id, target_id, kind in to_insert:
            self.conn.execute(
                "INSERT OR IGNORE INTO edges (source_id, target_id, kind) VALUES (?, ?, ?)",
                (source_id, target_id, kind),
            )
        self.conn.commit()
        return resolved_count

    # --- Query methods ---

    def get_file_dependents(self, file_path: str) -> list[str]:
        """Get files that depend on (import) the given file."""
        module_id = f"{file_path}::module"
        rows = self.conn.execute(
            """
            SELECT DISTINCT n.file_path
            FROM edges e
            JOIN nodes n ON n.id = e.source_id
            WHERE e.target_id = ? AND e.kind = 'imports'
            """,
            (module_id,),
        ).fetchall()
        return [r["file_path"] for r in rows]

    def get_file_dependencies(self, file_path: str) -> list[str]:
        """Get files that the given file depends on (imports)."""
        module_id = f"{file_path}::module"
        rows = self.conn.execute(
            """
            SELECT DISTINCT n.file_path
            FROM edges e
            JOIN nodes n ON n.id = e.target_id
            WHERE e.source_id = ? AND e.kind = 'imports'
            """,
            (module_id,),
        ).fetchall()
        return [r["file_path"] for r in rows]

    def get_callers(self, node_id: str) -> list[dict]:
        """Get functions that call the given function."""
        rows = self.conn.execute(
            """
            SELECT n.id, n.file_path, n.name, n.kind, n.signature
            FROM edges e
            JOIN nodes n ON n.id = e.source_id
            WHERE e.target_id = ? AND e.kind = 'calls'
            """,
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_callees(self, node_id: str) -> list[dict]:
        """Get functions called by the given function."""
        rows = self.conn.execute(
            """
            SELECT n.id, n.file_path, n.name, n.kind, n.signature
            FROM edges e
            JOIN nodes n ON n.id = e.target_id
            WHERE e.source_id = ? AND e.kind = 'calls'
            """,
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tests_for_file(self, file_path: str) -> list[dict]:
        """Get test functions that test code in the given file."""
        node_ids = [
            r["id"]
            for r in self.conn.execute(
                "SELECT id FROM nodes WHERE file_path = ?", (file_path,)
            )
        ]
        if not node_ids:
            return []

        placeholders = ",".join("?" * len(node_ids))
        rows = self.conn.execute(
            f"""
            SELECT n.id, n.file_path, n.name, n.kind, n.signature
            FROM edges e
            JOIN nodes n ON n.id = e.source_id
            WHERE e.target_id IN ({placeholders}) AND e.kind = 'tests'
            """,
            node_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_nodes_in_file(self, file_path: str) -> list[dict]:
        """Get all nodes in a file."""
        rows = self.conn.execute(
            "SELECT id, file_path, name, kind, start_line, end_line, signature FROM nodes WHERE file_path = ?",
            (file_path,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_nodes(self, query: str) -> list[dict]:
        """Search nodes by name."""
        rows = self.conn.execute(
            "SELECT id, file_path, name, kind, signature FROM nodes WHERE name LIKE ? AND kind != 'module' LIMIT 50",
            (f"%{query}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get graph statistics."""
        nodes_count = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges_count = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        files_count = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

        edge_kinds = self.conn.execute(
            "SELECT kind, COUNT(*) as count FROM edges GROUP BY kind"
        ).fetchall()

        node_kinds = self.conn.execute(
            "SELECT kind, COUNT(*) as count FROM nodes GROUP BY kind"
        ).fetchall()

        return {
            "total_nodes": nodes_count,
            "total_edges": edges_count,
            "total_files": files_count,
            "edges_by_kind": {r["kind"]: r["count"] for r in edge_kinds},
            "nodes_by_kind": {r["kind"]: r["count"] for r in node_kinds},
        }

    def close(self) -> None:
        self.conn.close()
