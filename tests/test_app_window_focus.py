from __future__ import annotations

import unittest
from pathlib import Path

from skills.app_catalog import APP_PATHS_SOURCE, CatalogApp
from skills.app_window_focus import focus_app_window
from skills.named_window import NamedWindowResult


def make_app(name: str = "Discord") -> CatalogApp:
    return CatalogApp(
        display_name=name,
        normalized_name=name.casefold(),
        launch_path=Path(r"C:\Fake\App.lnk"),
        source=APP_PATHS_SOURCE,
    )


class AppWindowFocusTests(unittest.TestCase):
    def test_focuses_exact_app_window(self):
        app = make_app()
        calls = []

        result = focus_app_window(
            "Discord",
            resolve_app=lambda _: (app,),
            control_window=lambda resolved_app, action: calls.append(
                (resolved_app.display_name, action)
            ) or NamedWindowResult(
                success=True,
                message="Brought Discord to the foreground, sir.",
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.display_name, "Discord")
        self.assertEqual(
            result.message,
            "Brought Discord to the foreground, sir.",
        )
        self.assertEqual(calls, [("Discord", "bring_up")])

    def test_returns_window_control_failure(self):
        app = make_app()

        result = focus_app_window(
            "Discord",
            resolve_app=lambda _: (app,),
            control_window=lambda _, __: NamedWindowResult(
                success=False,
                message=(
                    "Windows would not bring Discord to the "
                    "foreground, sir."
                ),
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "Windows would not bring Discord to the foreground, sir.",
        )

    def test_rejects_missing_exact_app(self):
        result = focus_app_window(
            "Discord",
            resolve_app=lambda _: (),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not find an exact local app named Discord, sir.",
        )

    def test_rejects_ambiguous_exact_apps(self):
        result = focus_app_window(
            "Discord",
            resolve_app=lambda _: (make_app(), make_app()),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I found 2 exact local apps named Discord. I will not "
            "guess which one to bring to the foreground, sir.",
        )

    def test_rejects_empty_app_name(self):
        result = focus_app_window(" ")

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I cannot focus an empty app name, sir.",
        )


if __name__ == "__main__":
    unittest.main()