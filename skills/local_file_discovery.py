from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import FILE_SEARCH_ROOTS


DEFAULT_FILE_SEARCH_MAX_RESULTS = 20
DEFAULT_FILE_SEARCH_MAX_FILES_SCANNED = 10_000
MAX_FILE_SEARCH_QUERY_LENGTH = 200
_ALPHANUMERIC_SEGMENT_PATTERN = re.compile(
    r"[A-Za-z0-9]+"
)

_CAMEL_CASE_TERM_PATTERN = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|\d|$)"
    r"|[A-Z]?[a-z]+"
    r"|[0-9]+"
)

SKIPPED_FILE_SEARCH_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "$recycle.bin",
        "system volume information",
    }
)


class LocalFileDiscoveryError(RuntimeError):
    """Raised when local file discovery cannot run safely."""


@dataclass(frozen=True)
class LocalFileMatch:
    """One file found below an explicitly approved root."""

    file_name: str
    extension: str
    root_path: str
    relative_path: str
    modified_at_utc: str
    size_bytes: int


@dataclass(frozen=True)
class LocalFileSearchReport:
    """One bounded filename-only local file-search result."""

    query: str
    matches: tuple[LocalFileMatch, ...]
    searched_roots: tuple[str, ...]
    unavailable_roots: tuple[str, ...]
    files_scanned: int
    skipped_directories: int
    scan_limit_reached: bool
    result_limit_reached: bool

def _split_query_terms(
    value: str,
) -> tuple[str, ...]:
    """Split user query text without interpreting its capitalization."""
    return tuple(
        segment.casefold()
        for segment in _ALPHANUMERIC_SEGMENT_PATTERN.findall(value)
    )


def _split_filename_terms(
    value: str,
) -> tuple[str, ...]:
    """Split filenames by separators and camel case without substrings."""
    terms: list[str] = []

    for segment in _ALPHANUMERIC_SEGMENT_PATTERN.findall(value):
        camel_terms = tuple(
            term.casefold()
            for term in _CAMEL_CASE_TERM_PATTERN.findall(segment)
        )

        if not camel_terms:
            continue

        terms.extend(camel_terms)

        combined_term = "".join(camel_terms)

        if combined_term not in camel_terms:
            terms.append(combined_term)

    return tuple(terms)

def _normalise_query(value: str) -> str:
    """Validate one literal filename-search query."""
    if not isinstance(value, str):
        raise LocalFileDiscoveryError(
            "A file search query must contain text."
        )

    query = " ".join(value.split())

    if not query:
        raise LocalFileDiscoveryError(
            "A file search query cannot be empty."
        )

    if len(query) > MAX_FILE_SEARCH_QUERY_LENGTH:
        raise LocalFileDiscoveryError(
            "A file search query is too long."
        )

    return query


def _validate_positive_limit(
    value: int,
    *,
    label: str,
) -> int:
    """Accept one positive bounded search limit."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise LocalFileDiscoveryError(
            f"{label} must be a positive integer."
        )

    return value


def _is_reparse_point(path: Path) -> bool:
    """Reject symbolic links and Windows junctions."""
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True

    is_junction = getattr(path, "is_junction", None)

    if callable(is_junction):
        try:
            return bool(is_junction())
        except OSError:
            return True

    return False


def _normalise_root(value: Path) -> Path:
    """Accept only one absolute, non-drive-root search folder."""
    if not isinstance(value, Path):
        raise LocalFileDiscoveryError(
            "A file-search root must be a path."
        )

    root = value.expanduser()

    if not root.is_absolute():
        raise LocalFileDiscoveryError(
            "A file-search root must be an absolute path."
        )

    if root == Path(root.anchor):
        raise LocalFileDiscoveryError(
            "A drive root cannot be a file-search root."
        )

    return root


def _deduplicate_roots(
    roots: Iterable[Path],
) -> tuple[Path, ...]:
    """Keep configured roots stable and unique."""
    unique_roots: list[Path] = []
    seen_roots: set[str] = set()

    for raw_root in roots:
        root = _normalise_root(raw_root)
        identity = os.path.normcase(
            os.path.normpath(str(root))
        )

        if identity in seen_roots:
            continue

        seen_roots.add(identity)
        unique_roots.append(root)

    return tuple(unique_roots)


def _prepare_search_roots(
    roots: Iterable[Path],
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Return usable approved roots without changing configuration."""
    configured_roots = _deduplicate_roots(roots)

    if not configured_roots:
        raise LocalFileDiscoveryError(
            "No safe file-search roots are configured."
        )

    usable_roots: list[Path] = []
    unavailable_roots: list[str] = []

    for root in configured_roots:
        try:
            unavailable = (
                _is_reparse_point(root)
                or not root.exists()
                or not root.is_dir()
            )
        except OSError:
            unavailable = True

        if unavailable:
            unavailable_roots.append(str(root))
            continue

        usable_roots.append(root)

    if not usable_roots:
        raise LocalFileDiscoveryError(
            "No configured safe file-search roots are available."
        )

    return tuple(usable_roots), tuple(unavailable_roots)

def format_local_file_search_scope(
    *,
    roots: Iterable[Path] = FILE_SEARCH_ROOTS,
) -> str:
    """Describe the approved filename-only search scope."""
    available_roots, unavailable_roots = _prepare_search_roots(
        roots
    )

    lines = [
        "Approved local file search",
        (
            "Avens searches filenames only. It does not open files "
            "or read file contents."
        ),
        "",
        "Available approved roots:",
        *(
            f"- {root}"
            for root in available_roots
        ),
    ]

    if unavailable_roots:
        lines.extend(
            (
                "",
                "Unavailable configured roots:",
                *(
                    f"- {root}"
                    for root in unavailable_roots
                ),
            )
        )

    lines.extend(
        (
            "",
            "Commands:",
            "- Find file <terms>",
            "- Search files <terms>",
            "- What files can you search?",
        )
    )

    return "\n".join(lines)

def _format_utc_timestamp(timestamp: float) -> str:
    """Format one filesystem timestamp as stable UTC text."""
    return (
        datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _format_file_size(size_bytes: int) -> str:
    """Return one compact human-readable byte count."""
    if size_bytes < 1_024:
        return f"{size_bytes} B"

    if size_bytes < 1_024 * 1_024:
        return f"{size_bytes / 1_024:.1f} KB"

    if size_bytes < 1_024 * 1_024 * 1_024:
        return f"{size_bytes / (1_024 * 1_024):.1f} MB"

    return f"{size_bytes / (1_024 * 1_024 * 1_024):.1f} GB"


def search_local_files(
    query: str,
    *,
    roots: Iterable[Path] = FILE_SEARCH_ROOTS,
    max_results: int = DEFAULT_FILE_SEARCH_MAX_RESULTS,
    max_files_scanned: int = (
        DEFAULT_FILE_SEARCH_MAX_FILES_SCANNED
    ),
) -> LocalFileSearchReport:
    """Search approved folders by filename only and never follow links."""
    normalised_query = _normalise_query(query)
    result_limit = _validate_positive_limit(
        max_results,
        label="The file-search result limit",
    )
    scan_limit = _validate_positive_limit(
        max_files_scanned,
        label="The file-search scan limit",
    )
    search_roots, unavailable_roots = _prepare_search_roots(
        roots
    )

    query_terms = _split_query_terms(normalised_query)

    if not query_terms:
        raise LocalFileDiscoveryError(
            "A file search query must include letters or numbers."
        )
    candidates: list[tuple[float, LocalFileMatch]] = []
    searched_roots: list[str] = []
    unavailable_root_labels = list(unavailable_roots)
    files_scanned = 0
    skipped_directories = 0
    scan_limit_reached = False

    for root in search_roots:
        pending_directories = [root]
        root_was_scanned = False

        while pending_directories:
            current_directory = pending_directories.pop()

            try:
                with os.scandir(current_directory) as entries:
                    ordered_entries = tuple(
                        sorted(
                            entries,
                            key=lambda entry: (
                                entry.name.casefold(),
                                entry.name,
                            ),
                        )
                    )
            except OSError:
                if (
                    current_directory == root
                    and str(root)
                    not in unavailable_root_labels
                ):
                    unavailable_root_labels.append(str(root))

                continue

            if current_directory == root:
                root_was_scanned = True

            for entry in ordered_entries:
                if files_scanned >= scan_limit:
                    scan_limit_reached = True
                    break

                candidate_path = Path(entry.path)

                try:
                    if (
                        entry.is_symlink()
                        or _is_reparse_point(candidate_path)
                    ):
                        continue

                    if entry.is_dir(follow_symlinks=False):
                        if (
                            entry.name.casefold()
                            in SKIPPED_FILE_SEARCH_DIRECTORY_NAMES
                        ):
                            skipped_directories += 1
                            continue

                        pending_directories.append(candidate_path)
                        continue

                    if not entry.is_file(follow_symlinks=False):
                        continue

                    files_scanned += 1
                    file_name = entry.name
                    file_name_terms = _split_filename_terms(
                        file_name
                    )

                    if not all(
                        term in file_name_terms
                        for term in query_terms
                    ):
                        continue

                    file_stats = entry.stat(
                        follow_symlinks=False
                    )
                    relative_path = candidate_path.relative_to(root)

                    match = LocalFileMatch(
                        file_name=file_name,
                        extension=candidate_path.suffix.casefold(),
                        root_path=str(root),
                        relative_path=str(relative_path),
                        modified_at_utc=_format_utc_timestamp(
                            file_stats.st_mtime
                        ),
                        size_bytes=file_stats.st_size,
                    )

                    candidates.append(
                        (file_stats.st_mtime, match)
                    )
                except OSError:
                    continue

            if scan_limit_reached:
                break

        if root_was_scanned:
            searched_roots.append(str(root))

        if scan_limit_reached:
            break

    if not searched_roots:
        raise LocalFileDiscoveryError(
            "No configured safe file-search roots could be scanned."
        )

    ordered_candidates = tuple(
        match
        for _, match in sorted(
            candidates,
            key=lambda item: (
                -item[0],
                item[1].root_path.casefold(),
                item[1].relative_path.casefold(),
            ),
        )
    )

    return LocalFileSearchReport(
        query=normalised_query,
        matches=ordered_candidates[:result_limit],
        searched_roots=tuple(searched_roots),
        unavailable_roots=tuple(unavailable_root_labels),
        files_scanned=files_scanned,
        skipped_directories=skipped_directories,
        scan_limit_reached=scan_limit_reached,
        result_limit_reached=(
            len(ordered_candidates) > result_limit
        ),
    )


def format_local_file_search(
    report: LocalFileSearchReport,
) -> str:
    """Format one local filename search for console inspection."""
    if not isinstance(report, LocalFileSearchReport):
        raise LocalFileDiscoveryError(
            "A local file-search report is invalid."
        )

    lines = [
        f'Local file search: "{report.query}"',
        (
            "Roots scanned: "
            f"{len(report.searched_roots)} | "
            f"Files checked: {report.files_scanned} | "
            f"Skipped folders: {report.skipped_directories}"
        ),
    ]

    if report.unavailable_roots:
        lines.extend(
            (
                "",
                "Unavailable approved roots:",
                *(
                    f"- {root}"
                    for root in report.unavailable_roots
                ),
            )
        )

    if report.scan_limit_reached:
        lines.extend(
            (
                "",
                (
                    "Scan limit reached. Narrow the filename query "
                    "for a more complete result."
                ),
            )
        )

    lines.extend(("", "Matches:"))

    if not report.matches:
        lines.append("- None")
        return "\n".join(lines)

    for index, match in enumerate(report.matches, start=1):
        extension = match.extension or "no extension"

        lines.extend(
            (
                (
                    f"{index}. "
                    f"[{extension} | "
                    f"modified {match.modified_at_utc} | "
                    f"{_format_file_size(match.size_bytes)}] "
                    f"{match.file_name}"
                ),
                f"   Root: {match.root_path}",
                f"   Path: {match.relative_path}",
            )
        )

    if report.result_limit_reached:
        lines.extend(
            (
                "",
                (
                    "Showing the first "
                    f"{len(report.matches)} matching files."
                ),
            )
        )

    return "\n".join(lines)