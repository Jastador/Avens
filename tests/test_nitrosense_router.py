from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from skills.nitrosense_confirmation import (
    NitroSenseGamingProfileConfirmationStore,
)
from skills.router import route_local_skill
from tools.nitrosense_gaming_profile import (
    NitroSenseControlError,
    NitroSenseGamingProfileReport,
)


class FrozenClock:
    """Tiny controllable UTC clock for confirmation tests."""

    def __init__(self) -> None:
        self.now = datetime(2026, 7, 8, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def make_report(
    *,
    performance_changed: bool = True,
    fan_max_changed: bool = True,
) -> NitroSenseGamingProfileReport:
    """Build one deterministic verified NitroSense result."""
    return NitroSenseGamingProfileReport(
        performance_changed=performance_changed,
        fan_max_changed=fan_max_changed,
        performance_selected=True,
        fan_max_selected=True,
    )


class NitroSenseRouterTests(unittest.TestCase):
    def test_nitrosense_request_requires_confirmation(self):
        store = NitroSenseGamingProfileConfirmationStore()

        result = route_local_skill(
            "Set NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
            apply_nitrosense_profile=lambda: self.fail(
                "should not apply before confirmation"
            ),
        )

        self.assertEqual(
            result.skill_name,
            "set_nitrosense_gaming_profile",
        )
        self.assertTrue(result.requires_confirmation)
        self.assertIn(
            "Confirm NitroSense gaming profile",
            result.message,
        )

    def test_confirmed_nitrosense_request_applies_verified_profile(self):
        store = NitroSenseGamingProfileConfirmationStore()
        output = []
        applied = []

        route_local_skill(
            "Enable gaming performance",
            nitrosense_gaming_profile_confirmations=store,
            apply_nitrosense_profile=lambda: self.fail(
                "initial request should not apply"
            ),
        )

        def apply_profile() -> NitroSenseGamingProfileReport:
            applied.append(True)
            return make_report()

        result = route_local_skill(
            "Confirm NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
            apply_nitrosense_profile=apply_profile,
            console_output=output.append,
        )

        self.assertEqual(applied, [True])
        self.assertEqual(
            result.message,
            "NitroSense gaming profile applied and verified, sir.",
        )
        self.assertIn(
            "Performance: changed",
            "\n".join(output),
        )
        self.assertIn(
            "Fan Max: changed",
            "\n".join(output),
        )
        self.assertIn(
            "Visual verification: Performance=True | Fan Max=True",
            "\n".join(output),
        )

    def test_confirm_without_pending_request_is_safe(self):
        store = NitroSenseGamingProfileConfirmationStore()

        result = route_local_skill(
            "Confirm NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
            apply_nitrosense_profile=lambda: self.fail(
                "nothing should apply"
            ),
        )

        self.assertEqual(
            result.message,
            (
                "There is no pending NitroSense gaming profile "
                "request to confirm, sir."
            ),
        )

    def test_cancel_pending_nitrosense_request(self):
        store = NitroSenseGamingProfileConfirmationStore()

        route_local_skill(
            "Max out NitroSense fans",
            nitrosense_gaming_profile_confirmations=store,
        )

        result = route_local_skill(
            "Cancel NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
        )

        self.assertEqual(
            result.message,
            "Pending NitroSense gaming profile request cancelled, sir.",
        )

        after_cancel = route_local_skill(
            "Confirm NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
        )

        self.assertEqual(
            after_cancel.message,
            (
                "There is no pending NitroSense gaming profile "
                "request to confirm, sir."
            ),
        )

    def test_expired_confirmation_does_not_apply(self):
        clock = FrozenClock()
        store = NitroSenseGamingProfileConfirmationStore(
            ttl_seconds=10,
            clock=clock,
        )

        route_local_skill(
            "Set NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
        )

        clock.advance(seconds=11)

        result = route_local_skill(
            "Confirm NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
            apply_nitrosense_profile=lambda: self.fail(
                "expired request should not apply"
            ),
        )

        self.assertEqual(
            result.message,
            (
                "That NitroSense gaming profile confirmation "
                "expired. Ask me to set it again, sir."
            ),
        )

    def test_nitrosense_controller_failure_is_reported_safely(self):
        store = NitroSenseGamingProfileConfirmationStore()
        output = []

        route_local_skill(
            "Set NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
        )

        def fail_apply() -> NitroSenseGamingProfileReport:
            raise NitroSenseControlError("test failure")

        result = route_local_skill(
            "Confirm NitroSense gaming profile",
            nitrosense_gaming_profile_confirmations=store,
            apply_nitrosense_profile=fail_apply,
            console_output=output.append,
        )

        self.assertEqual(
            result.message,
            (
                "I could not safely apply the NitroSense gaming "
                "profile, sir."
            ),
        )
        self.assertIn(
            "NitroSense control error: test failure",
            output,
        )


if __name__ == "__main__":
    unittest.main()