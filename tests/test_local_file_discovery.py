from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.local_file_discovery import (
    LocalFileDiscoveryError,
    format_local_file_search,
    search_local_files,
    format_local_file_search_scope,
)

def write_file(
    root: Path,
    relative_path: str,
    content: str = "",
) -> Path:
    """Create one test file below a temporary approved root."""
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination

class LocalFileDiscoveryTests(unittest.TestCase):

    def test_scope_formatter_lists_available_and_unavailable_roots(
        self,
    ):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing_root = root / "missing"

            formatted = format_local_file_search_scope(
                roots=(root, missing_root),
            )

        self.assertIn(
            "Approved local file search",
            formatted,
        )
        self.assertIn(
            "filenames only",
            formatted,
        )
        self.assertIn(str(root), formatted)
        self.assertIn(
            "Unavailable configured roots:",
            formatted,
        )
        self.assertIn(str(missing_root), formatted)
        self.assertIn("Find file <terms>", formatted)
        self.assertIn(
            "What files can you search?",
            formatted,
        )

    def test_search_requires_configured_roots(self):
        with self.assertRaisesRegex(
            LocalFileDiscoveryError,
            "No safe file-search roots",
        ):
            search_local_files(
                "roadmap",
                roots=(),
            )

    def test_search_matches_all_filename_terms_case_insensitively(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            write_file(
                root,
                "Plans/Avens Roadmap 2026.md",
            )
            write_file(
                root,
                "Plans/Avens Notes.md",
            )

            report = search_local_files(
                "aVeNs ROADMAP",
                roots=(root,),
            )

        self.assertEqual(
            [match.file_name for match in report.matches],
            ["Avens Roadmap 2026.md"],
        )

    def test_search_avoids_partial_word_false_positives(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            write_file(
                root,
                "AvensApp-current.patch",
            )
            write_file(
                root,
                "btcc_toyota_avensis.ini",
            )

            report = search_local_files(
                "avens",
                roots=(root,),
            )

        self.assertEqual(
            [match.file_name for match in report.matches],
            ["AvensApp-current.patch"],
        )

    def test_search_rejects_queries_without_filename_terms(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            with self.assertRaisesRegex(
                LocalFileDiscoveryError,
                "letters or numbers",
            ):
                search_local_files(
                    "!!!",
                    roots=(root,),
                )

    def test_search_uses_filenames_not_file_contents(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            write_file(
                root,
                "ordinary.txt",
                "Avens roadmap private content",
            )

            report = search_local_files(
                "avens roadmap",
                roots=(root,),
            )

        self.assertEqual(report.matches, ())

    def test_search_returns_relative_path_and_metadata(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = write_file(
                root,
                "Projects/MarketLens.py",
                "print('hello')",
            )

            expected_size = destination.stat().st_size

            report = search_local_files(
                "marketlens",
                roots=(root,),
            )

        match = report.matches[0]

        self.assertEqual(match.file_name, "MarketLens.py")
        self.assertEqual(match.extension, ".py")
        self.assertEqual(match.root_path, str(root))
        self.assertEqual(
            match.relative_path,
            str(Path("Projects") / "MarketLens.py"),
        )
        self.assertEqual(match.size_bytes, expected_size)
        self.assertTrue(match.modified_at_utc.endswith("Z"))

    def test_search_skips_common_noise_directories(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            write_file(
                root,
                ".git/Avens Roadmap.md",
            )
            write_file(
                root,
                "node_modules/Avens Roadmap.md",
            )
            write_file(
                root,
                "Plans/Avens Roadmap.md",
            )

            report = search_local_files(
                "avens roadmap",
                roots=(root,),
            )

        self.assertEqual(
            [match.relative_path for match in report.matches],
            [str(Path("Plans") / "Avens Roadmap.md")],
        )
        self.assertEqual(report.skipped_directories, 2)

    def test_missing_root_is_reported_when_another_root_works(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing_root = root / "missing"

            write_file(
                root,
                "Avens Roadmap.md",
            )

            report = search_local_files(
                "roadmap",
                roots=(missing_root, root),
            )

        self.assertEqual(
            report.unavailable_roots,
            (str(missing_root),),
        )
        self.assertEqual(
            report.searched_roots,
            (str(root),),
        )

    def test_all_unavailable_roots_are_rejected(self):
        with TemporaryDirectory() as temporary_directory:
            missing_root = (
                Path(temporary_directory)
                / "missing"
            )

            with self.assertRaisesRegex(
                LocalFileDiscoveryError,
                "No configured safe file-search roots are available",
            ):
                search_local_files(
                    "roadmap",
                    roots=(missing_root,),
                )

    def test_relative_and_drive_root_paths_are_rejected(self):
        with self.assertRaisesRegex(
            LocalFileDiscoveryError,
            "must be an absolute path",
        ):
            search_local_files(
                "roadmap",
                roots=(Path("relative-folder"),),
            )

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            with self.assertRaisesRegex(
                LocalFileDiscoveryError,
                "drive root",
            ):
                search_local_files(
                    "roadmap",
                    roots=(Path(root.anchor),),
                )

    def test_scan_limit_is_reported(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            write_file(root, "a.txt")
            write_file(root, "b.txt")
            write_file(root, "c.txt")

            report = search_local_files(
                "missing",
                roots=(root,),
                max_files_scanned=1,
            )

        self.assertEqual(report.files_scanned, 1)
        self.assertTrue(report.scan_limit_reached)

    def test_result_limit_and_formatter_are_reported(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            write_file(root, "Avens Roadmap A.md")
            write_file(root, "Avens Roadmap B.md")
            write_file(root, "Avens Roadmap C.md")

            report = search_local_files(
                "avens roadmap",
                roots=(root,),
                max_results=2,
            )

        formatted = format_local_file_search(report)

        self.assertEqual(len(report.matches), 2)
        self.assertTrue(report.result_limit_reached)
        self.assertIn(
            'Local file search: "avens roadmap"',
            formatted,
        )
        self.assertIn("Matches:", formatted)
        self.assertIn(
            "Showing the first 2 matching files.",
            formatted,
        )

    def test_search_skips_symbolic_linked_directories(self):
        with TemporaryDirectory() as temporary_directory, TemporaryDirectory() as outside_directory:
            root = Path(temporary_directory)
            outside_root = Path(outside_directory)

            write_file(
                outside_root,
                "Avens Roadmap.md",
            )
            linked_directory = root / "linked"

            try:
                os.symlink(
                    outside_root,
                    linked_directory,
                    target_is_directory=True,
                )
            except OSError:
                self.skipTest(
                    "Symbolic links are unavailable in this environment."
                )

            report = search_local_files(
                "avens roadmap",
                roots=(root,),
            )

        self.assertEqual(report.matches, ())