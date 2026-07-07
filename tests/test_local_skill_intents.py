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
            "List apps",
            "List all apps",
            "Show apps",
            "Search apps chrome",
            "Find app visual studio",
            "What can I control?",
            "What can I do with Chrome?",
            "Take a note buy chicken tomorrow",
            "Add note finish Avens tests",
            "Show my notes",
            "List notes",
            "Search notes chicken",
            "Delete note 2",
            "Confirm delete note 2",
            "Cancel delete note",
            "Set volume to 70",
            "Increase volume",
            "Decrease volume by 15",
            "Mute volume",
            "Unmute volume",
            "What is the volume?",
            "Set brightness to 50",
            "Decrease brightness by 10",
            "What is brightness?",
            "Open Night Light settings",
            "Start reading setup",
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
            "Search apps",
            "What can I do with?",
            "Take a note",
            "Search notes",
            "Remember that I like tea",
            "Delete note",
            "Confirm delete note",
            "Delete note two",
            "Set volume",
            "Increase volume by",
            "Set brightness",
            "Decrease brightness by",
            "Night Light settings",
            "Reading setup",
        )

        for user_input in non_commands:
            with self.subTest(user_input=user_input):
                self.assertFalse(
                    is_explicit_local_skill_request(user_input)
                )

        self.assertFalse(is_explicit_local_skill_request(None))