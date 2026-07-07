from __future__ import annotations

import unittest
from unittest.mock import patch

from core import wake_word


class WakeWordDeliveryTests(unittest.TestCase):
    def test_stop_check_handles_no_callback(self):
        self.assertFalse(
            wake_word._should_stop_wait(None)
        )

    def test_stop_check_returns_callback_result(self):
        self.assertTrue(
            wake_word._should_stop_wait(lambda: True)
        )
        self.assertFalse(
            wake_word._should_stop_wait(lambda: False)
        )

    def test_stop_check_fails_open_when_callback_errors(self):
        output = []

        result = wake_word._should_stop_wait(
            lambda: (_ for _ in ()).throw(
                RuntimeError("test failure")
            )
        )

        self.assertFalse(result)

    def test_wake_listener_exits_before_loading_audio_when_stop_requested(
        self,
    ):
        with patch.object(
            wake_word,
            "get_wake_model",
        ) as get_wake_model:
            result = wake_word.listen_for_wake_word(
                should_stop=lambda: True
            )

        self.assertFalse(result)
        get_wake_model.assert_not_called()