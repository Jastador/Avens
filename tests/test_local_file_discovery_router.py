from __future__ import annotations

import unittest

from skills.local_file_discovery import (
    LocalFileDiscoveryError,
    LocalFileMatch,
    LocalFileSearchReport,
)
from skills.router import route_local_skill


def make_match(
    file_name: str,
) -> LocalFileMatch:
    """Build one stable filename-only search match."""
    return LocalFileMatch(
        file_name=file_name,
        extension=".md",
        root_path=r"C:\Projects\VSCode",
        relative_path=rf"Avens\{file_name}",
        modified_at_utc="2026-07-08T08:30:00Z",
        size_bytes=512,
    )


def make_report(
    query: str,
    *,
    matches: tuple[LocalFileMatch, ...] = (),
    result_limit_reached: bool = False,
) -> LocalFileSearchReport:
    """Build one stable local file-search report."""
    return LocalFileSearchReport(
        query=query,
        matches=matches,
        searched_roots=(r"C:\Projects\VSCode",),
        unavailable_roots=(),
        files_scanned=12,
        skipped_directories=2,
        scan_limit_reached=False,
        result_limit_reached=result_limit_reached,
    )


class LocalFileDiscoveryRouterTests(unittest.TestCase):
    def test_find_file_prints_read_only_result(self):
        output = []
        queries = []
        report = make_report(
            "Avens roadmap",
            matches=(make_match("Avens Roadmap.md"),),
        )

        def find_local_files(query: str) -> LocalFileSearchReport:
            queries.append(query)
            return report

        result = route_local_skill(
            "Find file Avens roadmap",
            find_local_files=find_local_files,
            format_local_file_search_report=lambda _: (
                "formatted filename-only report"
            ),
            console_output=output.append,
        )

        self.assertEqual(queries, ["Avens roadmap"])
        self.assertEqual(
            result.skill_name,
            "search_local_files",
        )
        self.assertEqual(
            result.message,
            "I printed 1 approved local file match, sir.",
        )
        self.assertEqual(
            output,
            ["formatted filename-only report"],
        )

    def test_search_files_supports_alternate_phrase_and_no_matches(self):
        queries = []

        def find_local_files(query: str) -> LocalFileSearchReport:
            queries.append(query)
            return make_report("budget")

        result = route_local_skill(
            "Search files budget",
            find_local_files=find_local_files,
            format_local_file_search_report=lambda _: "no matches",
        )

        self.assertEqual(queries, ["budget"])
        self.assertEqual(
            result.message,
            'I found no approved local files matching "budget", sir.',
        )

    def test_file_search_errors_are_reported_safely(self):
        output = []

        def find_local_files(_: str) -> LocalFileSearchReport:
            raise LocalFileDiscoveryError("test failure")

        result = route_local_skill(
            "Find file Avens roadmap",
            find_local_files=find_local_files,
            console_output=output.append,
        )

        self.assertEqual(
            result.message,
            (
                "I could not safely search the configured local "
                "folders, sir."
            ),
        )
        self.assertIn(
            "Local file discovery error: test failure",
            output,
        )

    def test_file_search_scope_prints_approved_locations(self):
        output = []

        result = route_local_skill(
            "What files can you search?",
            describe_local_file_search_scope=lambda: (
                "Approved local file search"
            ),
            console_output=output.append,
        )

        self.assertEqual(
            result.skill_name,
            "show_local_file_search_scope",
        )
        self.assertEqual(
            result.message,
            "I printed the approved local file-search scope, sir.",
        )
        self.assertEqual(
            output,
            ["Approved local file search"],
        )