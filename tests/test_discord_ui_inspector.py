from __future__ import annotations

from types import SimpleNamespace
import unittest

from skills.discord_ui_inspector import (
    DiscordUiInspection,
    format_discord_ui_inspection,
    inspect_discord_ui,
)
from skills.named_window import NamedWindowMatchResult


class DiscordUiInspectorTests(unittest.TestCase):
    @staticmethod
    def _discord_app() -> SimpleNamespace:
        return SimpleNamespace(display_name="Discord")

    def test_inspects_one_foreground_discord_window(self):
        result = inspect_discord_ui(
            resolve_app=lambda _: (self._discord_app(),),
            inspect_windows=lambda app: NamedWindowMatchResult(
                display_name=app.display_name,
                window_handles=(101,),
                error_message=None,
            ),
            get_window_title=lambda _: (
                "#🎧│music 1.0 | Illuminatiz👁⃤ - Discord"
            ),
            get_foreground_window=lambda: 101,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.display_name, "Discord")
        self.assertEqual(result.window_count, 1)
        self.assertEqual(len(result.windows), 1)
        self.assertEqual(result.windows[0].window_handle, 101)
        self.assertEqual(
            result.windows[0].title,
            "#🎧│music 1.0 | Illuminatiz👁⃤ - Discord",
        )
        self.assertTrue(result.windows[0].is_foreground)
        self.assertEqual(
            result.message,
            "Discord UI inspection found 1 verified window. "
            "One verified Discord window is currently foreground, sir.",
        )

    def test_reports_missing_exact_discord_app(self):
        result = inspect_discord_ui(
            resolve_app=lambda _: (),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(result.windows, ())
        self.assertEqual(
            result.message,
            "I could not find an exact local app named Discord, sir.",
        )

    def test_reports_ambiguous_exact_discord_apps(self):
        result = inspect_discord_ui(
            resolve_app=lambda _: (
                self._discord_app(),
                self._discord_app(),
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(
            result.message,
            "I found 2 exact local apps named Discord. I will not "
            "guess which one to inspect, sir.",
        )

    def test_reports_window_inspection_error(self):
        result = inspect_discord_ui(
            resolve_app=lambda _: (self._discord_app(),),
            inspect_windows=lambda _: NamedWindowMatchResult(
                display_name="Discord",
                window_handles=(),
                error_message="Could not inspect Discord safely.",
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(
            result.message,
            "Could not inspect Discord safely.",
        )

    def test_reports_no_verified_discord_window(self):
        result = inspect_discord_ui(
            resolve_app=lambda _: (self._discord_app(),),
            inspect_windows=lambda _: NamedWindowMatchResult(
                display_name="Discord",
                window_handles=(),
                error_message=None,
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(
            result.message,
            "Discord is not open with a verified window, sir.",
        )

    def test_title_read_failure_does_not_fail_inspection(self):
        def raise_title_error(_: int) -> str:
            raise OSError("title unavailable")

        result = inspect_discord_ui(
            resolve_app=lambda _: (self._discord_app(),),
            inspect_windows=lambda app: NamedWindowMatchResult(
                display_name=app.display_name,
                window_handles=(202,),
                error_message=None,
            ),
            get_window_title=raise_title_error,
            get_foreground_window=lambda: 999,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.window_count, 1)
        self.assertEqual(result.windows[0].title, "")
        self.assertFalse(result.windows[0].is_foreground)
        self.assertEqual(
            result.message,
            "Discord UI inspection found 1 verified window. "
            "No verified Discord window is currently foreground, sir.",
        )

    def test_formats_inspection_report(self):
        inspection = DiscordUiInspection(
            success=True,
            display_name="Discord",
            window_count=1,
            windows=(),
            message="Discord UI inspection found 1 verified window.",
        )

        self.assertEqual(
            format_discord_ui_inspection(inspection),
            "\n".join(
                [
                    "Discord UI inspection:",
                    "Status: success",
                    (
                        "Message: Discord UI inspection found "
                        "1 verified window."
                    ),
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()