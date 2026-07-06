from __future__ import annotations

import unittest

from skills.router import is_explicit_local_skill_request


class LocalSkillIntentTests(unittest.TestCase):
    def test_recognizes_explicit_local_skill_requests(self):
        requests = (
            "Open Notepad",
            "Open, Calculator",
            "Refresh app list",
            "Minimize this",
            "Restore Chrome",
            "Bring up Chrome",
            "Close Chrome",
            "Confirm, close Chrome",
            "Cancel",
        )

        for user_input in requests:
            with self.subTest(user_input=user_input):
                self.assertTrue(
                    is_explicit_local_skill_request(user_input)
                )

    def test_rejects_non_commands_and_partial_transcripts(self):
        non_commands = (
            "",
            "Notepad.",
            "What does Notepad do?",
            "How do I close a file safely?",
            "Why do people minimize windows?",
            "I do not want you to open anything.",
            "Go to sleep",
        )

        for user_input in non_commands:
            with self.subTest(user_input=user_input):
                self.assertFalse(
                    is_explicit_local_skill_request(user_input)
                )

        self.assertFalse(is_explicit_local_skill_request(None))