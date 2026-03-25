"""Tree-sitter AST parser for extracting code structure across languages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser, Node


# Language instances
PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())

LANGUAGE_MAP = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": TS_LANGUAGE,
}

# Extension to language key
EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


@dataclass
class CodeNode:
    """A code entity (function, class, method) extracted from AST."""

    id: str  # "file_path::name"
    file_path: str
    name: str
    kind: str  # function, class, method, module
    start_line: int
    end_line: int
    signature: str = ""


@dataclass
class CodeEdge:
    """A relationship between code entities."""

    source_id: str
    target_id: str
    kind: str  # calls, imports, inherits, tests


@dataclass
class ParseResult:
    """Result of parsing a single file."""

    file_path: str
    language: str
    nodes: list[CodeNode] = field(default_factory=list)
    edges: list[CodeEdge] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


# --- Language-specific extraction ---

def _extract_python(tree: Node, file_path: str) -> ParseResult:
    """Extract nodes and edges from a Python AST."""
    result = ParseResult(file_path=file_path, language="python")
    root = tree

    def _visit(node: Node, parent_class: str | None = None) -> None:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode()
                kind = "method" if parent_class else "function"
                full_name = f"{parent_class}.{name}" if parent_class else name
                node_id = f"{file_path}::{full_name}"

                # Build signature
                params_node = node.child_by_field_name("parameters")
                params = params_node.text.decode() if params_node else "()"
                sig = f"def {full_name}{params}"

                result.nodes.append(
                    CodeNode(
                        id=node_id,
                        file_path=file_path,
                        name=full_name,
                        kind=kind,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=sig,
                    )
                )

                # Extract call sites within this function
                _extract_calls(node, node_id, file_path, result)

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = name_node.text.decode()
                node_id = f"{file_path}::{class_name}"

                # Check for superclasses
                superclasses = node.child_by_field_name("superclasses")
                sig = f"class {class_name}"
                if superclasses:
                    sig += superclasses.text.decode()

                result.nodes.append(
                    CodeNode(
                        id=node_id,
                        file_path=file_path,
                        name=class_name,
                        kind="class",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=sig,
                    )
                )

                # Check inheritance edges
                if superclasses:
                    for arg in superclasses.children:
                        if arg.type == "identifier":
                            base_name = arg.text.decode()
                            result.edges.append(
                                CodeEdge(
                                    source_id=node_id,
                                    target_id=f"?::{base_name}",
                                    kind="inherits",
                                )
                            )

                # Visit children with class context
                for child in node.children:
                    _visit(child, parent_class=class_name)
                return

        elif node.type in ("import_statement", "import_from_statement"):
            _extract_python_import(node, file_path, result)

        for child in node.children:
            _visit(child, parent_class)

    _visit(root)
    return result


def _extract_python_import(node: Node, file_path: str, result: ParseResult) -> None:
    """Extract import information from Python import statements."""
    text = node.text.decode().strip()

    if node.type == "import_from_statement":
        # from X import Y
        module_node = node.child_by_field_name("module_name")
        if module_node:
            module = module_node.text.decode()
            result.imports.append(module)
            result.edges.append(
                CodeEdge(
                    source_id=f"{file_path}::module",
                    target_id=f"?::{module}",
                    kind="imports",
                )
            )
    elif node.type == "import_statement":
        # import X
        for child in node.children:
            if child.type == "dotted_name":
                module = child.text.decode()
                result.imports.append(module)
                result.edges.append(
                    CodeEdge(
                        source_id=f"{file_path}::module",
                        target_id=f"?::{module}",
                        kind="imports",
                    )
                )


def _extract_js_ts(tree: Node, file_path: str, language: str) -> ParseResult:
    """Extract nodes and edges from JavaScript/TypeScript AST."""
    result = ParseResult(file_path=file_path, language=language)
    root = tree

    def _visit(node: Node, parent_class: str | None = None) -> None:
        # Function declarations
        if node.type in ("function_declaration", "method_definition"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode()
                kind = "method" if parent_class else "function"
                full_name = f"{parent_class}.{name}" if parent_class else name
                node_id = f"{file_path}::{full_name}"

                params_node = node.child_by_field_name("parameters")
                params = params_node.text.decode() if params_node else "()"
                sig = f"function {full_name}{params}"

                result.nodes.append(
                    CodeNode(
                        id=node_id,
                        file_path=file_path,
                        name=full_name,
                        kind=kind,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=sig,
                    )
                )
                _extract_calls(node, node_id, file_path, result)

        # Arrow functions assigned to variables
        elif node.type == "lexical_declaration" or node.type == "variable_declaration":
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    name_node = declarator.child_by_field_name("name")
                    value_node = declarator.child_by_field_name("value")
                    if (
                        name_node
                        and value_node
                        and value_node.type == "arrow_function"
                    ):
                        name = name_node.text.decode()
                        node_id = f"{file_path}::{name}"
                        params_node = value_node.child_by_field_name("parameters")
                        params = params_node.text.decode() if params_node else "()"
                        sig = f"const {name} = {params} =>"

                        result.nodes.append(
                            CodeNode(
                                id=node_id,
                                file_path=file_path,
                                name=name,
                                kind="function",
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                signature=sig,
                            )
                        )
                        _extract_calls(value_node, node_id, file_path, result)

        # Class declarations
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = name_node.text.decode()
                node_id = f"{file_path}::{class_name}"
                sig = f"class {class_name}"

                # Check for extends
                heritage = node.child_by_field_name("heritage")
                if heritage:
                    sig += f" {heritage.text.decode()}"

                result.nodes.append(
                    CodeNode(
                        id=node_id,
                        file_path=file_path,
                        name=class_name,
                        kind="class",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=sig,
                    )
                )

                for child in node.children:
                    _visit(child, parent_class=class_name)
                return

        # Import statements
        elif node.type == "import_statement":
            source = node.child_by_field_name("source")
            if source:
                module = source.text.decode().strip("'\"")
                result.imports.append(module)
                result.edges.append(
                    CodeEdge(
                        source_id=f"{file_path}::module",
                        target_id=f"?::{module}",
                        kind="imports",
                    )
                )

        for child in node.children:
            _visit(child, parent_class)

    _visit(root)
    return result


def _extract_calls(
    node: Node, caller_id: str, file_path: str, result: ParseResult
) -> None:
    """Extract function call sites within a node."""
    if node.type == "call" or node.type == "call_expression":
        func_node = node.child_by_field_name("function")
        if func_node:
            call_name = func_node.text.decode()
            # Skip built-ins and common patterns
            if not call_name.startswith(("print", "len", "str", "int", "float", "list", "dict", "set", "tuple", "super", "range", "enumerate", "isinstance", "type", "hasattr", "getattr", "setattr")):
                result.edges.append(
                    CodeEdge(
                        source_id=caller_id,
                        target_id=f"?::{call_name}",
                        kind="calls",
                    )
                )

    for child in node.children:
        _extract_calls(child, caller_id, file_path, result)


# --- Public API ---

def parse_file(file_path: str, language: str, source: bytes | None = None) -> ParseResult:
    """Parse a single file and extract code structure.

    Args:
        file_path: Path to the source file.
        language: Language key (python, javascript, typescript).
        source: Optional source bytes. If None, reads from file_path.

    Returns:
        ParseResult with extracted nodes, edges, and imports.
    """
    if language not in LANGUAGE_MAP:
        return ParseResult(file_path=file_path, language=language)

    if source is None:
        source = Path(file_path).read_bytes()

    ts_language = LANGUAGE_MAP[language]

    # Handle TSX
    ext = Path(file_path).suffix
    if ext == ".tsx":
        ts_language = TSX_LANGUAGE

    parser = Parser(ts_language)
    tree = parser.parse(source)

    if language == "python":
        result = _extract_python(tree.root_node, file_path)
    elif language in ("javascript", "typescript"):
        result = _extract_js_ts(tree.root_node, file_path, language)
    else:
        result = ParseResult(file_path=file_path, language=language)

    # Add a module-level node for every file
    result.nodes.insert(
        0,
        CodeNode(
            id=f"{file_path}::module",
            file_path=file_path,
            name="module",
            kind="module",
            start_line=1,
            end_line=tree.root_node.end_point[0] + 1,
            signature=file_path,
        ),
    )

    return result


def detect_tests(file_path: str, nodes: list[CodeNode]) -> list[CodeEdge]:
    """Detect test functions and create test edges."""
    edges: list[CodeEdge] = []
    rel = file_path.lower()
    is_test_file = (
        "test_" in rel
        or "_test." in rel
        or ".test." in rel
        or ".spec." in rel
        or "/tests/" in rel
        or "/test/" in rel
        or "/__tests__/" in rel
    )
    if not is_test_file:
        return edges

    for node in nodes:
        if node.kind in ("function", "method"):
            name_lower = node.name.lower()
            if name_lower.startswith("test") or name_lower.startswith("it_"):
                # Try to guess what it tests based on naming
                # test_authenticate -> authenticate
                tested_name = node.name
                for prefix in ("test_", "test", "it_"):
                    if tested_name.lower().startswith(prefix):
                        tested_name = tested_name[len(prefix) :]
                        break

                if tested_name:
                    edges.append(
                        CodeEdge(
                            source_id=node.id,
                            target_id=f"?::{tested_name}",
                            kind="tests",
                        )
                    )

    return edges
