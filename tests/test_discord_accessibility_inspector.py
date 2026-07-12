from __future__ import annotations

import unittest

from skills.discord_accessibility_inspector import (
    DiscordAccessibilityInspection,
    DiscordAccessibilityNode,
    format_discord_accessibility_inspection,
    inspect_discord_accessibility,
)
from skills.discord_ui_inspector import (
    DiscordUiInspection,
    DiscordWindowSnapshot,
)


class DiscordAccessibilityInspectorTests(unittest.TestCase):
    def test_inspects_accessibility_nodes_for_one_window(self):
        def inspect_discord() -> DiscordUiInspection:
            return DiscordUiInspection(
                success=True,
                display_name="Discord",
                window_count=1,
                windows=(
                    DiscordWindowSnapshot(
                        window_handle=101,
                        title="#music | Test Server - Discord",
                        is_foreground=True,
                    ),
                ),
                message="Discord UI inspection found 1 verified window.",
            )

        def collect_nodes(
            window_handle: int,
            *,
            max_nodes: int,
        ) -> tuple[DiscordAccessibilityNode, ...]:
            self.assertEqual(window_handle, 101)
            self.assertEqual(max_nodes, 200)

            return (
                DiscordAccessibilityNode(
                    index=1,
                    name="Test Server",
                    control_type="Text",
                    class_name="TextBlock",
                    automation_id="",
                ),
                DiscordAccessibilityNode(
                    index=2,
                    name="music",
                    control_type="ListItem",
                    class_name="",
                    automation_id="channel-voice",
                ),
            )

        result = inspect_discord_accessibility(
            inspect_discord=inspect_discord,
            collect_nodes=collect_nodes,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.window_handle, 101)
        self.assertEqual(
            result.window_title,
            "#music | Test Server - Discord",
        )
        self.assertEqual(result.node_count, 2)
        self.assertEqual(result.nodes[0].name, "Test Server")
        self.assertEqual(result.nodes[1].automation_id, "channel-voice")
        self.assertEqual(
            result.message,
            "Discord accessibility inspection found 2 readable "
            "UI elements, sir.",
        )

    def test_reports_failed_discord_window_inspection(self):
        result = inspect_discord_accessibility(
            inspect_discord=lambda: DiscordUiInspection(
                success=False,
                display_name="Discord",
                window_count=0,
                windows=(),
                message="Discord is not open.",
            ),
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.window_handle)
        self.assertEqual(result.node_count, 0)
        self.assertEqual(result.message, "Discord is not open.")

    def test_requires_exactly_one_verified_discord_window(self):
        result = inspect_discord_accessibility(
            inspect_discord=lambda: DiscordUiInspection(
                success=True,
                display_name="Discord",
                window_count=2,
                windows=(
                    DiscordWindowSnapshot(
                        window_handle=101,
                        title="One - Discord",
                        is_foreground=False,
                    ),
                    DiscordWindowSnapshot(
                        window_handle=202,
                        title="Two - Discord",
                        is_foreground=False,
                    ),
                ),
                message="Discord UI inspection found 2 windows.",
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.node_count, 0)
        self.assertEqual(
            result.message,
            "I need exactly one verified Discord window before "
            "inspecting accessibility, sir.",
        )

    def test_reports_empty_accessibility_tree(self):
        result = inspect_discord_accessibility(
            inspect_discord=lambda: DiscordUiInspection(
                success=True,
                display_name="Discord",
                window_count=1,
                windows=(
                    DiscordWindowSnapshot(
                        window_handle=101,
                        title="Discord",
                        is_foreground=False,
                    ),
                ),
                message="Discord UI inspection found 1 window.",
            ),
            collect_nodes=lambda *_args, **_kwargs: (),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_handle, 101)
        self.assertEqual(result.window_title, "Discord")
        self.assertEqual(result.node_count, 0)
        self.assertEqual(
            result.message,
            "Discord accessibility inspection found no readable "
            "UI elements, sir.",
        )

    def test_reports_collect_error_safely(self):
        def raise_collect_error(
            *_args: object,
            **_kwargs: object,
        ) -> tuple[DiscordAccessibilityNode, ...]:
            raise RuntimeError("uia unavailable")

        result = inspect_discord_accessibility(
            inspect_discord=lambda: DiscordUiInspection(
                success=True,
                display_name="Discord",
                window_count=1,
                windows=(
                    DiscordWindowSnapshot(
                        window_handle=101,
                        title="Discord",
                        is_foreground=False,
                    ),
                ),
                message="Discord UI inspection found 1 window.",
            ),
            collect_nodes=raise_collect_error,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_handle, 101)
        self.assertEqual(
            result.message,
            "I could not inspect Discord accessibility safely: "
            "uia unavailable",
        )

    def test_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            inspect_discord_accessibility(max_nodes=0)

        with self.assertRaises(ValueError):
            format_discord_accessibility_inspection(
                DiscordAccessibilityInspection(
                    success=True,
                    window_handle=101,
                    window_title="Discord",
                    node_count=0,
                    nodes=(),
                    message="ok",
                ),
                max_nodes_to_show=0,
            )

    def test_formats_accessibility_inspection(self):
        inspection = DiscordAccessibilityInspection(
            success=True,
            window_handle=101,
            window_title="#music | Test Server - Discord",
            node_count=2,
            nodes=(
                DiscordAccessibilityNode(
                    index=1,
                    name="Test Server",
                    control_type="Text",
                    class_name="TextBlock",
                    automation_id="",
                ),
                DiscordAccessibilityNode(
                    index=2,
                    name="music",
                    control_type="ListItem",
                    class_name="",
                    automation_id="channel-voice",
                ),
            ),
            message=(
                "Discord accessibility inspection found 2 readable "
                "UI elements, sir."
            ),
        )

        formatted = format_discord_accessibility_inspection(
            inspection,
            max_nodes_to_show=1,
        )

        self.assertIn("Status: success", formatted)
        self.assertIn("Window: 0x65", formatted)
        self.assertIn("name=Test Server", formatted)
        self.assertIn("... 1 more nodes not shown.", formatted)


if __name__ == "__main__":
    unittest.main()