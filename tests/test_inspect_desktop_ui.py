from __future__ import annotations

import re
import unittest

from tools.inspect_desktop_ui import (
    ControlSnapshot,
    compile_filters,
    control_matches_filters,
    format_snapshot,
    parse_arguments,
)


class DesktopUiInspectorTests(unittest.TestCase):
    def test_list_windows_does_not_require_title_regex(self):
        arguments = parse_arguments(["--list-windows"])

        self.assertTrue(arguments.list_windows)
        self.assertIsNone(arguments.title_regex)

    def test_inspection_requires_title_regex_without_window_list(self):
        with self.assertRaises(SystemExit) as raised:
            parse_arguments([])

        self.assertEqual(raised.exception.code, 2)

    def test_filters_match_control_metadata_case_insensitively(self):
        snapshot = ControlSnapshot(
            name="Maximum Fan Speed",
            control_type="Button",
            automation_id="FanMaxButton",
            class_name="Button",
            handle="12345",
            depth=2,
        )
        filters = compile_filters(("fan|max",))

        self.assertTrue(
            control_matches_filters(snapshot, filters),
        )

    def test_empty_filters_allow_every_control(self):
        snapshot = ControlSnapshot(
            name="Performance",
            control_type="RadioButton",
            automation_id="PerformanceMode",
            class_name="Button",
            handle="54321",
            depth=1,
        )

        self.assertTrue(
            control_matches_filters(snapshot, ()),
        )

    def test_snapshot_format_includes_read_only_identifiers(self):
        snapshot = ControlSnapshot(
            name="Join Voice",
            control_type="Button",
            automation_id="JoinVoiceButton",
            class_name="Button",
            handle="67890",
            depth=1,
        )

        formatted = format_snapshot(snapshot)

        self.assertIn("name='Join Voice'", formatted)
        self.assertIn("type='Button'", formatted)
        self.assertIn(
            "automation_id='JoinVoiceButton'",
            formatted,
        )
        self.assertNotIn("click", formatted.casefold())


if __name__ == "__main__":
    unittest.main()