from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skills.local_routine_urls import (
    LocalRoutineUrlError,
    LocalRoutineUrlNotConfiguredError,
    load_approved_url_groups,
    open_approved_url_group,
)


class LocalRoutineUrlTests(unittest.TestCase):
    def test_missing_private_file_loads_no_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            url_file = Path(directory) / "missing.json"

            self.assertEqual(
                load_approved_url_groups(url_file=url_file),
                {},
            )

    def test_loads_https_url_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            url_file = Path(directory) / "routine_url_groups.json"
            url_file.write_text(
                json.dumps(
                    {
                        "study": [
                            "https://example.com/study",
                        ],
                        "market-prep": [
                            "https://kite.zerodha.com/",
                            "https://streak.zerodha.com/",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            groups = load_approved_url_groups(url_file=url_file)

            self.assertEqual(
                groups["study"],
                ("https://example.com/study",),
            )
            self.assertEqual(
                groups["market prep"],
                (
                    "https://kite.zerodha.com/",
                    "https://streak.zerodha.com/",
                ),
            )

    def test_rejects_non_https_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            url_file = Path(directory) / "routine_url_groups.json"
            url_file.write_text(
                json.dumps(
                    {
                        "study": [
                            "http://example.com/study",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineUrlError):
                load_approved_url_groups(url_file=url_file)

    def test_rejects_empty_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            url_file = Path(directory) / "routine_url_groups.json"
            url_file.write_text(
                json.dumps(
                    {
                        "study": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineUrlError):
                load_approved_url_groups(url_file=url_file)

    def test_open_group_opens_only_configured_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            url_file = Path(directory) / "routine_url_groups.json"
            url_file.write_text(
                json.dumps(
                    {
                        "study": [
                            "https://example.com/one",
                            "https://example.com/two",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            opened_urls = []

            report = open_approved_url_group(
                "study",
                url_file=url_file,
                open_url=lambda url: opened_urls.append(url) or True,
            )

            self.assertEqual(
                report.opened_urls,
                (
                    "https://example.com/one",
                    "https://example.com/two",
                ),
            )
            self.assertEqual(
                opened_urls,
                [
                    "https://example.com/one",
                    "https://example.com/two",
                ],
            )

    def test_missing_group_raises_not_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            url_file = Path(directory) / "routine_url_groups.json"
            url_file.write_text(
                json.dumps(
                    {
                        "study": [
                            "https://example.com/study",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineUrlNotConfiguredError):
                open_approved_url_group(
                    "market",
                    url_file=url_file,
                    open_url=lambda _: True,
                )


if __name__ == "__main__":
    unittest.main()