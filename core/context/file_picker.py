"""Rules-based file picker (P4-001a, D-P4-9/10/12). No LLM.

Merges spec contract, planner hints, and ripgrep symbol hits into a ranked,
auditable candidate list fed to assemble_context(). Backend-neutral — output
is paths only; Aider mapping stays in core/engine/aider_engine.py.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.engine.git_diff import normalize_repo_path
from core.specs.delegation_policies import EDIT_SCOPE_DISCOVER, DelegationPolicies
from core.workspace.walk import should_skip_dir, should_skip_file

MAX_SYMBOL_QUERIES = 20
MAX_FILES_PER_SYMBOL = 10
DEFAULT_MAX_DISCOVERED = 30
MIN_SYMBOL_LENGTH = 3

SCAN_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".yaml", ".yml", ".toml")

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "not", "with", "this", "that", "from", "into",
        "are", "was", "were", "has", "have", "had", "but", "all", "any",
        "test", "tests", "file", "files", "path", "paths", "spec", "task",
        "code", "data", "list", "dict", "str", "int", "bool", "none",
        "true", "false", "def", "class", "import", "return", "self",
        "new", "old", "use", "uses", "via", "per", "see", "etc", "may",
    }
)

_BACKTICK_RE = re.compile(r"`([^`\n]{1,80})`")
_DEF_CLASS_RE = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

SOURCE_SPEC_EDIT = "spec_edit"
SOURCE_SPEC_READ = "spec_read"
SOURCE_HINT = "hint"
SOURCE_SYMBOL_SCAN = "symbol_scan"
SOURCE_WORKSPACE_RAG = "workspace_rag"


@dataclass
class CandidateFilesResult:
    ranked_paths: list[str] = field(default_factory=list)
    edit_paths: list[str] = field(default_factory=list)
    read_paths: list[str] = field(default_factory=list)
    discovered_read: list[str] = field(default_factory=list)
    suggested_edit_paths: list[str] = field(default_factory=list)
    symbol_queries: list[str] = field(default_factory=list)
    path_sources: dict[str, str] = field(default_factory=dict)

    def to_audit_dict(self) -> dict[str, list[str]]:
        """Compact summary for metadata / JSONL (no payloads)."""
        data: dict[str, list[str]] = {
            "ranked_paths": self.ranked_paths,
            "discovered_read": self.discovered_read,
            "suggested_edit_paths": self.suggested_edit_paths,
            "symbol_queries": self.symbol_queries,
        }
        workspace_rag = [
            p for p, src in self.path_sources.items() if src == SOURCE_WORKSPACE_RAG
        ]
        if workspace_rag:
            data["workspace_rag_paths"] = sorted(workspace_rag)
        return data


def max_discovered_paths() -> int:
    raw = os.environ.get("MCP_CODER_PICKER_MAX_DISCOVERED", "").strip()
    try:
        val = int(raw)
        return val if val > 0 else DEFAULT_MAX_DISCOVERED
    except (ValueError, TypeError):
        return DEFAULT_MAX_DISCOVERED


def extract_symbol_queries(task: str, spec_text: str | None) -> list[str]:
    """v0 heuristics: backtick identifiers + def/class names; capped, deduped.

    Case-sensitive dedupe (Python symbols); min length 3; stopwords dropped;
    path-like backtick contents (contain '/') are skipped — paths come from
    the spec contract, not the symbol scan.
    """
    text = task + "\n" + (spec_text or "")
    seen: set[str] = set()
    queries: list[str] = []

    def _add(candidate: str) -> None:
        sym = candidate.strip()
        if len(sym) < MIN_SYMBOL_LENGTH:
            return
        if "/" in sym or " " in sym:
            return
        if not _IDENTIFIER_RE.match(sym):
            return
        if sym.lower() in _STOPWORDS:
            return
        if sym in seen:
            return
        seen.add(sym)
        queries.append(sym)

    for match in _BACKTICK_RE.finditer(text):
        if len(queries) >= MAX_SYMBOL_QUERIES:
            break
        # Strip trailing call parens/extensions so `foo()` and `bar.py` match content
        raw = match.group(1).strip().rstrip("()")
        if raw.endswith((".py", ".md", ".yaml", ".yml", ".json", ".toml")):
            continue
        _add(raw)

    for match in _DEF_CLASS_RE.finditer(text):
        if len(queries) >= MAX_SYMBOL_QUERIES:
            break
        _add(match.group(1))

    return queries[:MAX_SYMBOL_QUERIES]


def _rg_available() -> bool:
    return shutil.which("rg") is not None


def _scan_symbol_rg(workspace: Path, symbol: str) -> list[str]:
    cmd = ["rg", "-l", "--fixed-strings", symbol]
    for ext in SCAN_EXTENSIONS:
        cmd.extend(["-g", f"*{ext}"])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode not in (0, 1):
        return []
    hits = [normalize_repo_path(line) for line in proc.stdout.splitlines() if line.strip()]
    return [h for h in hits if h][:MAX_FILES_PER_SYMBOL]


def _iter_scannable_files(workspace: Path) -> list[Path]:
    """Workspace text files matching SCAN_EXTENSIONS, same skip rules as walk_workspace."""
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(workspace, topdown=True):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for filename in filenames:
            if should_skip_file(filename):
                continue
            if not filename.endswith(SCAN_EXTENSIONS):
                continue
            results.append(Path(dirpath) / filename)
    return results


def _scan_symbols_fallback(
    workspace: Path, symbols: list[str]
) -> dict[str, list[str]]:
    """Pure-Python scan when rg is missing. Returns symbol → hit paths."""
    hits: dict[str, list[str]] = {s: [] for s in symbols}
    root = workspace.resolve()
    for abs_path in _iter_scannable_files(root):
        try:
            text = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = normalize_repo_path(abs_path.relative_to(root).as_posix())
        except ValueError:
            continue
        if not rel:
            continue
        for symbol in symbols:
            if len(hits[symbol]) >= MAX_FILES_PER_SYMBOL:
                continue
            if symbol in text:
                hits[symbol].append(rel)
    return hits


def scan_symbols(workspace: Path, symbols: list[str]) -> dict[str, list[str]]:
    """Per-symbol file hits; rg subprocess when available, Python fallback otherwise."""
    if not symbols:
        return {}
    if _rg_available():
        return {s: _scan_symbol_rg(workspace, s) for s in symbols}
    return _scan_symbols_fallback(workspace, symbols)


def _edit_dirs(files_edit: list[str]) -> set[str]:
    dirs: set[str] = set()
    for path in files_edit:
        parent = str(Path(path).parent.as_posix())
        if parent and parent != ".":
            dirs.add(parent)
    return dirs


def pick_candidate_files(
    *,
    workspace: Path,
    task: str,
    spec_text: str | None,
    policies: DelegationPolicies,
    target_files: list[str],
    workspace_rag_paths: list[str] | None = None,
) -> CandidateFilesResult:
    """Rank candidate files: spec contract → planner hints → symbol discoveries.

    Discover mode (D-P4-12): symbol scan runs; discoveries become read context.
    Strict mode: no scan, no discoveries, no suggested edits.

    suggested_edit_paths rule (D-P4-12, audit only — never auto-promoted to
    edit-full per D-P4-10): a discovered path is "edit-like" when it sits in
    the same directory as one of the spec's files_edit entries. Discoveries
    outside edit dirs stay read-only context.
    """
    edit_paths = list(policies.files_edit)
    read_paths_spec = list(policies.files_read)
    contract = set(policies.all_paths)

    hint_paths = sorted(
        {
            norm
            for p in target_files
            if (norm := normalize_repo_path(p)) and norm not in contract
        }
    )

    path_sources: dict[str, str] = {}
    for p in edit_paths:
        path_sources[p] = SOURCE_SPEC_EDIT
    for p in read_paths_spec:
        path_sources.setdefault(p, SOURCE_SPEC_READ)
    for p in hint_paths:
        path_sources.setdefault(p, SOURCE_HINT)

    edit_set = set(edit_paths)
    workspace_rag_filtered: list[str] = []
    for raw in workspace_rag_paths or []:
        norm = normalize_repo_path(raw)
        if not norm or norm in contract or norm in edit_set:
            continue
        if norm not in workspace_rag_filtered:
            workspace_rag_filtered.append(norm)
            path_sources[norm] = SOURCE_WORKSPACE_RAG

    discover = policies.edit_scope == EDIT_SCOPE_DISCOVER
    symbol_queries: list[str] = []
    discovered_read: list[str] = []
    suggested_edit_paths: list[str] = []

    # Symbol scan always runs — provides read context regardless of scope mode.
    # Only suggested_edit_paths (new edit-target proposals) is gated on discover mode.
    discovered_set: set[str] = set(workspace_rag_filtered)
    symbol_queries = extract_symbol_queries(task, spec_text)
    known = contract | set(hint_paths) | set(workspace_rag_filtered)
    hits_by_symbol = scan_symbols(workspace, symbol_queries)
    cap = max_discovered_paths()
    for symbol in symbol_queries:
        for hit in hits_by_symbol.get(symbol, []):
            if hit in known or hit in discovered_set:
                continue
            if len(discovered_set) >= cap:
                break
            discovered_set.add(hit)
            path_sources.setdefault(hit, SOURCE_SYMBOL_SCAN)
    # Workspace RAG paths first, then symbol discoveries (stable order).
    discovered_read = workspace_rag_filtered + sorted(
        discovered_set - set(workspace_rag_filtered)
    )

    if discover:
        # Discover mode: propose additional edit targets found near existing edit dirs.
        edit_dirs = _edit_dirs(edit_paths)
        suggested_edit_paths = sorted(
            p
            for p in discovered_read
            if p not in workspace_rag_filtered
            and str(Path(p).parent.as_posix()) in edit_dirs
        )
    else:
        # Strict mode: workspace RAG goes to read context; no new edit suggestions.
        for p in workspace_rag_filtered:
            if p not in read_paths_spec and p not in hint_paths:
                read_paths_spec.append(p)

    ranked: list[str] = []
    for bucket in (
        sorted(edit_paths),
        sorted(set(read_paths_spec) - set(edit_paths)),
        hint_paths,
        workspace_rag_filtered,
        [p for p in discovered_read if p not in workspace_rag_filtered],
    ):
        for p in bucket:
            if p not in ranked:
                ranked.append(p)

    return CandidateFilesResult(
        ranked_paths=ranked,
        edit_paths=sorted(edit_paths),
        read_paths=sorted(
            set(read_paths_spec) | set(hint_paths) | set(discovered_read) | set(workspace_rag_filtered)
        ),
        discovered_read=discovered_read,
        suggested_edit_paths=suggested_edit_paths,
        symbol_queries=symbol_queries,
        path_sources=path_sources,
    )
