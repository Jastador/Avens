from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.brain import (
    _iter_cancellable_lines,
    get_response,
)
from core.generation_cancel import (
    GenerationCancellationToken,
)


class FakeStreamingResponse:
    def __init__(
        self,
        lines,
        *,
        after_first_line=None,
    ):
        self._lines = list(lines)
        self._after_first_line = (
            after_first_line
        )

    def iter_lines(self):
        for index, line in enumerate(
            self._lines
        ):
            yield line

            if (
                index == 0
                and self._after_first_line
                is not None
            ):
                self._after_first_line()


class CancellableBrainStreamTests(
    unittest.TestCase
):
    def test_stream_without_token_yields_all_lines(
        self,
    ):
        response = FakeStreamingResponse(
            [
                b"first",
                b"second",
            ]
        )

        lines = list(
            _iter_cancellable_lines(response)
        )

        self.assertEqual(
            lines,
            [
                b"first",
                b"second",
            ],
        )

    def test_precancelled_stream_yields_nothing(
        self,
    ):
        token = GenerationCancellationToken(
            generation_id=1
        )
        token.cancel("directed interruption")

        response = FakeStreamingResponse(
            [
                b"first",
                b"second",
            ]
        )

        lines = list(
            _iter_cancellable_lines(
                response,
                token,
            )
        )

        self.assertEqual(lines, [])

    def test_stream_stops_after_cancellation(
        self,
    ):
        token = GenerationCancellationToken(
            generation_id=1
        )

        response = FakeStreamingResponse(
            [
                b"first",
                b"second",
                b"third",
            ],
            after_first_line=lambda: (
                token.cancel(
                    "directed interruption"
                )
            ),
        )

        lines = list(
            _iter_cancellable_lines(
                response,
                token,
            )
        )

        self.assertEqual(
            lines,
            [b"first"],
        )

    @patch("core.brain.offline_ai")
    @patch(
        "core.brain.mode_controller.snapshot"
    )
    def test_get_response_forwards_token_to_local_brain(
        self,
        mock_snapshot,
        mock_offline_ai,
    ):
        token = GenerationCancellationToken(
            generation_id=7
        )
        expected_stream = object()

        mock_snapshot.return_value = (
            SimpleNamespace(
                brain_mode="offline",
                brain_provider=None,
            )
        )
        mock_offline_ai.return_value = (
            expected_stream
        )

        result = get_response(
            "Explain local models.",
            cancellation_token=token,
        )

        self.assertIs(
            result,
            expected_stream,
        )
        mock_offline_ai.assert_called_once_with(
            "Explain local models.",
            cancellation_token=token,
        )


if __name__ == "__main__":
    unittest.main()