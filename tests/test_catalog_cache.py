from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from skills.app_catalog import (
    CatalogApp,
    PACKAGED_APP_SOURCE,
    START_MENU_SOURCE,
    normalise_name,
)
from skills.app_launcher import (
    clear_catalog_cache,
    resolve_catalog_matches,
)


class CatalogCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_catalog_cache()

    def tearDown(self) -> None:
        clear_catalog_cache()

    @staticmethod
    def _regular_app(display_name: str) -> CatalogApp:
        return CatalogApp(
            display_name=display_name,
            normalized_name=normalise_name(display_name),
            launch_path=Path(f"{display_name}.lnk"),
            source=START_MENU_SOURCE,
        )

    @staticmethod
    def _packaged_app(display_name: str) -> CatalogApp:
        return CatalogApp(
            display_name=display_name,
            normalized_name=normalise_name(display_name),
            launch_path=None,
            source=PACKAGED_APP_SOURCE,
            app_user_model_id=(
                f"Example.{display_name.replace(' ', '')}"
                "_8wekyb3d8bbwe!App"
            ),
        )

    def test_reuses_regular_catalog_snapshot_between_requests(self):
        regular_catalog = (
            self._regular_app("Steam"),
            self._regular_app("Discord"),
        )

        with (
            patch(
                "skills.app_launcher.scan_local_app_catalog",
                return_value=regular_catalog,
            ) as scan_regular,
            patch(
                "skills.app_launcher.scan_packaged_apps",
            ) as scan_packaged,
        ):
            steam_matches = resolve_catalog_matches("Steam")
            discord_matches = resolve_catalog_matches("Discord")

        self.assertEqual(
            steam_matches,
            (regular_catalog[0],),
        )
        self.assertEqual(
            discord_matches,
            (regular_catalog[1],),
        )
        scan_regular.assert_called_once_with(
            include_packaged=False,
        )
        scan_packaged.assert_not_called()

    def test_reuses_packaged_catalog_snapshot_after_regular_miss(self):
        packaged_catalog = (
            self._packaged_app("Calculator"),
            self._packaged_app("Camera"),
        )

        with (
            patch(
                "skills.app_launcher.scan_local_app_catalog",
                return_value=(),
            ) as scan_regular,
            patch(
                "skills.app_launcher.scan_packaged_apps",
                return_value=packaged_catalog,
            ) as scan_packaged,
        ):
            calculator_matches = resolve_catalog_matches(
                "Calculator",
            )
            camera_matches = resolve_catalog_matches("Camera")

        self.assertEqual(
            calculator_matches,
            (packaged_catalog[0],),
        )
        self.assertEqual(
            camera_matches,
            (packaged_catalog[1],),
        )
        scan_regular.assert_called_once_with(
            include_packaged=False,
        )
        scan_packaged.assert_called_once_with(
            excluded_normalized_names=frozenset(),
        )

    def test_clear_catalog_cache_forces_fresh_regular_discovery(self):
        first_catalog = (self._regular_app("Steam"),)
        second_catalog = (self._regular_app("Discord"),)

        with patch(
            "skills.app_launcher.scan_local_app_catalog",
            side_effect=(first_catalog, second_catalog),
        ) as scan_regular:
            first_matches = resolve_catalog_matches("Steam")

            clear_catalog_cache()

            second_matches = resolve_catalog_matches("Discord")

        self.assertEqual(first_matches, first_catalog)
        self.assertEqual(second_matches, second_catalog)
        self.assertEqual(scan_regular.call_count, 2)


if __name__ == "__main__":
    unittest.main()