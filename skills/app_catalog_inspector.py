from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from skills.app_catalog import (
    APP_PATHS_SOURCE,
    PACKAGED_APP_SOURCE,
    START_MENU_SOURCE,
    CatalogApp,
    normalise_name,
)

SOURCE_ORDER = (
    START_MENU_SOURCE,
    APP_PATHS_SOURCE,
    PACKAGED_APP_SOURCE,
)

SOURCE_LABELS = {
    START_MENU_SOURCE: "Start Menu",
    APP_PATHS_SOURCE: "App Paths",
    PACKAGED_APP_SOURCE: "Packaged Apps",
}


@dataclass(frozen=True)
class CatalogReport:
    """One full read-only local app-catalog report."""

    entry_count: int
    alias_count: int
    text: str


@dataclass(frozen=True)
class CatalogSearchResult:
    """One deterministic local catalog search result."""

    query: str
    apps: tuple[CatalogApp, ...]
    aliases: tuple[tuple[str, str], ...]


def _catalog_sort_key(
    app: CatalogApp,
) -> tuple[str, str, str, str]:
    """Keep read-only catalog displays stable and deterministic."""
    return (
        app.display_name.casefold(),
        app.source,
        str(app.launch_path or ""),
        app.app_user_model_id or "",
    )


def _source_label(source: str) -> str:
    """Return a friendly stable label for one catalog source."""
    return SOURCE_LABELS.get(source, source.replace("_", " ").title())


def _normalised_aliases(
    aliases: Mapping[object, object],
) -> tuple[tuple[str, str], ...]:
    """Keep only valid alias pairs for read-only display and search."""
    cleaned_aliases: list[tuple[str, str]] = []

    for raw_alias, raw_target in aliases.items():
        if not isinstance(raw_alias, str) or not isinstance(raw_target, str):
            continue

        alias = normalise_name(raw_alias)
        target = normalise_name(raw_target)

        if not alias or not target:
            continue

        cleaned_aliases.append((alias, target))

    return tuple(sorted(cleaned_aliases))


def _display_name_lookup(
    apps: Iterable[CatalogApp],
) -> dict[str, str]:
    """Map one normalized catalog name to its first stable display name."""
    display_names: dict[str, str] = {}

    for app in apps:
        display_names.setdefault(
            app.normalized_name,
            app.display_name,
        )

    return display_names


def build_catalog_report(
    catalog: Iterable[CatalogApp],
    aliases: Mapping[object, object],
) -> CatalogReport:
    """Build a full grouped report without launching or resolving apps."""
    apps = tuple(sorted(catalog, key=_catalog_sort_key))
    alias_items = _normalised_aliases(aliases)
    display_names = _display_name_lookup(apps)

    lines = [
        "Avens Local App Catalog",
        f"Catalog entries: {len(apps)}",
        f"Configured aliases: {len(alias_items)}",
        "",
    ]

    known_sources = set(SOURCE_ORDER)
    extra_sources = tuple(
        sorted(
            {
                app.source
                for app in apps
                if app.source not in known_sources
            }
        )
    )

    for source in (*SOURCE_ORDER, *extra_sources):
        source_apps = tuple(
            app
            for app in apps
            if app.source == source
        )

        if not source_apps:
            continue

        lines.append(
            f"[{_source_label(source)}] ({len(source_apps)})"
        )

        for app in source_apps:
            lines.append(f"- {app.display_name}")

        lines.append("")

    lines.append("Aliases")

    if alias_items:
        for alias, target in alias_items:
            display_target = display_names.get(target, target)
            lines.append(f"- {alias} -> {display_target}")
    else:
        lines.append("- None configured")

    return CatalogReport(
        entry_count=len(apps),
        alias_count=len(alias_items),
        text="\n".join(lines),
    )


def write_catalog_report(
    report: CatalogReport,
    report_path: Path,
) -> Path:
    """Write one local report outside the repository."""
    destination = report_path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        f"{report.text}\n",
        encoding="utf-8",
    )

    return destination


def search_catalog(
    query: str,
    catalog: Iterable[CatalogApp],
    aliases: Mapping[object, object],
) -> CatalogSearchResult:
    """Find deterministic substring matches without resolving or launching."""
    normalized_query = normalise_name(query)

    if not normalized_query:
        return CatalogSearchResult(
            query="",
            apps=(),
            aliases=(),
        )

    apps = tuple(
        sorted(
            (
                app
                for app in catalog
                if normalized_query in app.normalized_name
            ),
            key=_catalog_sort_key,
        )
    )

    alias_items = tuple(
        (alias, target)
        for alias, target in _normalised_aliases(aliases)
        if (
            normalized_query in alias
            or normalized_query in target
        )
    )

    return CatalogSearchResult(
        query=normalized_query,
        apps=apps,
        aliases=alias_items,
    )


def format_catalog_search_result(
    result: CatalogSearchResult,
) -> str:
    """Format one deterministic catalog search for console output."""
    display_names = _display_name_lookup(result.apps)

    lines = [
        f'Catalog search: "{result.query}"',
        f"Catalog matches: {len(result.apps)}",
    ]

    if result.apps:
        for app in result.apps:
            lines.append(
                f"- {app.display_name} | {_source_label(app.source)}"
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            f"Alias matches: {len(result.aliases)}",
        ]
    )

    if result.aliases:
        for alias, target in result.aliases:
            display_target = display_names.get(target, target)
            lines.append(f"- {alias} -> {display_target}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def build_supported_controls_guide() -> str:
    """Return the fixed safe command guide for Avens local controls."""
    return "\n".join(
        (
            "Avens Safe Local Controls",
            "",
            "App launch:",
            "- Open <app>",
            "- Launch <app>",
            "- Start <app>",
            "",
            "Named app windows:",
            "- Minimize <app>",
            "- Maximize <app>",
            "- Restore <app>",
            "- Bring up <app>",
            "",
            "Focused window:",
            "- Minimize this",
            "- Maximize this",
            "- Restore this",
            "",
            "Close confirmation:",
            "- Close <app>",
            "- Close all <app> windows",
            "- Confirm close <app>",
            "- Confirm close all <app> windows",
            "- Cancel",
            "",
            "Local notes:",
            "- Take a note <text>",
            "- Add note <text>",
            "- Show my notes",
            "- List notes",
            "- Search notes <text>",
            "- Delete note <id>",
            "- Confirm delete note <id>",
            "- Cancel delete note",
            "",
            "Local reminders:",
            "- Set or start a timer for <duration>",
            "- Remind me to <task> in <duration>",
            "- Remind me tomorrow at <time> to <task>",
            "- List reminders",
            "- Cancel reminder <id>",
            "- Confirm cancel reminder <id>",
            "- Cancel reminder cancellation",
            "",
            "Local file discovery:",
            "- Find file <terms>",
            "- Search files <terms>",
            "- What files can you search?",
            "- Searches filenames only in approved folders.",
            "",
            "Local routines:",
            "- What routines do you have?",
            "- What does study mode do?",
            "- Start study mode",
            "- Start gaming mode",
            "- URL groups open only from private approved config.",
            "- Brightness and volume can be overridden in private settings.",
            "",
            "NitroSense gaming profile:",
            "- Set NitroSense gaming profile",
            "- Enable gaming performance",
            "- Max out NitroSense fans",
            "- Requires confirmation before changing laptop performance or fans.",
            "",
            "System controls:",
            "- What is the volume?",
            "- Set volume to <0-100>",
            "- Increase or decrease volume [by <1-100>]",
            "- Mute volume",
            "- Unmute volume",
            "- What is brightness?",
            "- Set brightness to <10-100>",
            "- Increase or decrease brightness [by <1-100>]",
            "- Open Night Light settings",
            "- Start reading setup",
            "",
            "Catalog inspection:",
            "- Refresh app list",
            "- List apps",
            "- List all apps",
            "- Show apps",
            "- Search apps <text>",
            "- Find app <text>",
            "- What can I control?",
            "- What can I do with <app>?",
            "",
            "System-control notes:",
            "- Night Light Settings opens the Windows page.",
            "- Avens does not claim to toggle Night Light itself.",
        )
    )


def build_app_controls_guide(
    app: CatalogApp,
) -> str:
    """Return the safe local controls available for one catalogued app."""
    display_name = app.display_name

    return "\n".join(
        (
            f"Controls for {display_name}",
            "",
            "Safe commands:",
            f"- Open {display_name}",
            f"- Minimize {display_name}",
            f"- Maximize {display_name}",
            f"- Restore {display_name}",
            f"- Bring up {display_name}",
            "",
            "Close confirmation:",
            f"- Close {display_name}",
            f"- Confirm close {display_name}",
            f"- Close all {display_name} windows",
            f"- Confirm close all {display_name} windows",
            "",
            "Notes:",
            "- Named window controls act only on exact catalog matches.",
            "- A close request always needs its exact confirmation phrase.",
            "- If multiple matching windows exist, Avens refuses to guess.",
        )
    )