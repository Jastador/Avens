from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd

from core.barge_intent import (
    BargeInDecision,
    BargeInIntent,
    classify_barge_in,
)
from core.generation_cancel_runtime import (
    cancel_generation_from_shared_state,
)
from core.stt import transcribe_recorded_audio
from utils.mic_check import get_active_mic
from utils.microphone_lock import microphone_lock


SAMPLE_RATE = 16000
BLOCK_SIZE = 800
BLOCK_DURATION_SECONDS = BLOCK_SIZE / SAMPLE_RATE


@dataclass
class SpeechCandidateRecorder:
    """Collect one possible spoken interruption.

    Loud blocks must be consecutive before recording is considered a real
    candidate. Once triggered, recording continues until trailing silence
    or the maximum capture length is reached.
    """

    start_threshold: float = 0.012
    end_threshold: float = 0.008
    required_start_hits: int = 3
    required_silence_blocks: int = 12
    maximum_capture_blocks: int = 120
    pre_roll_blocks: int = 6

    consecutive_start_hits: int = field(
        default=0,
        init=False,
    )
    trailing_silence_blocks: int = field(
        default=0,
        init=False,
    )
    triggered: bool = field(
        default=False,
        init=False,
    )
    finished: bool = field(
        default=False,
        init=False,
    )
    recorded_blocks: list[np.ndarray] = field(
        default_factory=list,
        init=False,
    )
    _pre_roll: deque[np.ndarray] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.start_threshold <= 0:
            raise ValueError(
                "start_threshold must be positive."
            )

        if self.end_threshold <= 0:
            raise ValueError(
                "end_threshold must be positive."
            )

        if self.end_threshold > self.start_threshold:
            raise ValueError(
                "end_threshold cannot exceed start_threshold."
            )

        if self.required_start_hits < 1:
            raise ValueError(
                "required_start_hits must be at least one."
            )

        if self.required_silence_blocks < 1:
            raise ValueError(
                "required_silence_blocks must be at least one."
            )

        if self.pre_roll_blocks < 1:
            raise ValueError(
                "pre_roll_blocks must be at least one."
            )

        if self.maximum_capture_blocks < self.pre_roll_blocks:
            raise ValueError(
                "maximum_capture_blocks must be at least "
                "as large as pre_roll_blocks."
            )

        self._pre_roll = deque(
            maxlen=self.pre_roll_blocks,
        )

    def reset_waiting_state(self) -> None:
        """Discard energy accumulated while Avens was not speaking."""

        if self.triggered:
            return

        self.consecutive_start_hits = 0
        self._pre_roll.clear()

    def add_block(
        self,
        audio_block,
        energy: float,
    ) -> str:
        """Process one microphone block.

        Returns one of:

        - ``waiting``
        - ``triggered``
        - ``capturing``
        - ``finished``
        - ``ignored``
        """

        if self.finished:
            return "ignored"

        block = np.asarray(
            audio_block,
            dtype=np.float32,
        ).reshape(-1).copy()

        if block.size == 0:
            return "ignored"

        if not self.triggered:
            self._pre_roll.append(block)

            if energy >= self.start_threshold:
                self.consecutive_start_hits += 1
            else:
                # Require consecutive loud blocks. Do not let humming,
                # clicks, or isolated noise accumulate over time.
                self.consecutive_start_hits = 0

            if (
                self.consecutive_start_hits
                < self.required_start_hits
            ):
                return "waiting"

            self.triggered = True
            self.recorded_blocks.extend(
                list(self._pre_roll)
            )
            self.trailing_silence_blocks = 0

            if (
                len(self.recorded_blocks)
                >= self.maximum_capture_blocks
            ):
                self.finished = True
                return "finished"

            return "triggered"

        self.recorded_blocks.append(block)

        if energy >= self.end_threshold:
            self.trailing_silence_blocks = 0
        else:
            self.trailing_silence_blocks += 1

        if (
            self.trailing_silence_blocks
            >= self.required_silence_blocks
        ):
            self.finished = True
            return "finished"

        if (
            len(self.recorded_blocks)
            >= self.maximum_capture_blocks
        ):
            self.finished = True
            return "finished"

        return "capturing"

    def audio(self) -> np.ndarray:
        """Return all recorded blocks as one flat float32 array."""

        if not self.recorded_blocks:
            return np.array(
                [],
                dtype=np.float32,
            )

        return np.concatenate(
            self.recorded_blocks
        ).astype(
            np.float32,
            copy=False,
        )


@dataclass(frozen=True)
class CapturedBargeIn:
    """Transcript and intent for one captured interruption."""

    transcript: str
    decision: BargeInDecision


def analyse_recorded_barge_in(
    audio_data,
    *,
    spoken_text: object = "",
) -> CapturedBargeIn:
    """Transcribe and classify one recorded interruption."""

    transcript = transcribe_recorded_audio(
        audio_data,
        command_aware=False,
    ).strip()

    decision = classify_barge_in(
        transcript,
        spoken_text=spoken_text,
    )

    return CapturedBargeIn(
        transcript=transcript,
        decision=decision,
    )


def _clear_barge_result(
    shared_state,
) -> None:
    shared_state["barge_in_transcript"] = ""
    shared_state["barge_in_intent"] = ""
    shared_state["barge_in_reason"] = ""
    shared_state["barge_in_confidence"] = 0.0
    shared_state["barge_in_ready"] = False
    shared_state["barge_in_status"] = "listening"
    shared_state[
        "barge_in_allow_transcription"
    ] = False


def _store_barge_result(
    shared_state,
    result: CapturedBargeIn,
) -> None:
    shared_state["barge_in_transcript"] = (
        result.transcript
    )
    shared_state["barge_in_intent"] = (
        result.decision.intent.value
    )
    shared_state["barge_in_reason"] = (
        result.decision.reason
    )
    shared_state["barge_in_confidence"] = (
        result.decision.confidence
    )
    shared_state["barge_in_ready"] = True
    shared_state["barge_in_status"] = "ready"


def listen_for_speech_interrupt(
    shared_state,
    threshold: float = 0.012,
    required_hits: int = 3,
    *,
    end_threshold: float = 0.008,
    trailing_silence_seconds: float = 0.6,
    maximum_capture_seconds: float = 6.0,
    pre_roll_seconds: float = 0.3,
):
    """Capture and classify speech heard while Avens is speaking.

    Detection first pauses speech provisionally. The listener then records
    the complete utterance, releases the microphone, transcribes the audio,
    and stores its classification in ``shared_state``.
    """

    microphone_id = get_active_mic()

    silence_blocks = max(
        1,
        round(
            trailing_silence_seconds
            / BLOCK_DURATION_SECONDS
        ),
    )

    maximum_blocks = max(
        1,
        round(
            maximum_capture_seconds
            / BLOCK_DURATION_SECONDS
        ),
    )

    pre_roll_blocks = max(
        1,
        round(
            pre_roll_seconds
            / BLOCK_DURATION_SECONDS
        ),
    )

    recorder = SpeechCandidateRecorder(
        start_threshold=threshold,
        end_threshold=end_threshold,
        required_start_hits=required_hits,
        required_silence_blocks=silence_blocks,
        maximum_capture_blocks=max(
            maximum_blocks,
            pre_roll_blocks,
        ),
        pre_roll_blocks=pre_roll_blocks,
    )

    spoken_text_snapshot = ""
    _clear_barge_result(shared_state)

    def callback(
        indata,
        frames,
        time_info,
        status,
    ):
        nonlocal spoken_text_snapshot

        del frames
        del time_info

        if status:
            print(
                "Barge-in input status: "
                f"{status}"
            )

        # Once capture has triggered, finish recording even if TTS has
        # already stopped and changed the shared speaking state.
        if not recorder.triggered:
            if shared_state.get(
                "stop_interrupt_listener",
                False,
            ):
                return

            if shared_state.get("state") != "speaking":
                recorder.reset_waiting_state()
                return

        audio = indata[:, 0]
        energy = float(
            np.sqrt(
                np.mean(audio ** 2)
            )
        )

        if energy > 0.006:
            print(
                f"Barge energy: {energy:.4f}"
            )

        event = recorder.add_block(
            audio,
            energy,
        )

        if event in {
            "triggered",
            "finished",
        } and not shared_state.get(
            "interrupt",
            False,
        ):
            spoken_text_snapshot = str(
                shared_state.get(
                    "current_spoken_text",
                    "",
                )
            )

            shared_state[
                "barge_in_status"
            ] = "capturing"

            # Pause TTS immediately, but do not yet decide whether the
            # sound was directed speech, background speech, echo, or noise.
            shared_state["interrupt"] = True

            generation_cancelled = (
                cancel_generation_from_shared_state(
                    shared_state,
                    reason=(
                        "provisional_speech_barge_in"
                    ),
                )
            )

            print(
                "Provisional speech barge-in detected. "
                f"Energy={energy:.4f}"
            )

            if generation_cancelled:
                print(
                    "🛑 Active brain generation "
                    "cancellation requested."
                )

    try:
        with microphone_lock:
            if shared_state.get(
                "stop_interrupt_listener",
                False,
            ):
                shared_state[
                    "barge_in_status"
                ] = "idle"
                return

            with sd.InputStream(
                device=microphone_id,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=callback,
            ):
                while True:
                    if recorder.triggered:
                        if recorder.finished:
                            break
                    elif shared_state.get(
                        "stop_interrupt_listener",
                        False,
                    ):
                        break

                    time.sleep(0.02)

        if not recorder.triggered:
            shared_state["barge_in_status"] = "idle"
            return

        shared_state["barge_in_status"] = "captured"

        # The app may still be draining an Ollama response.
        # Wait before starting GPU STT so both models do not
        # fight over the laptop's limited VRAM.
        while not shared_state.get(
            "barge_in_allow_transcription",
            False,
        ):
            time.sleep(0.02)

        shared_state["barge_in_status"] = "transcribing"

        result = analyse_recorded_barge_in(
            recorder.audio(),
            spoken_text=spoken_text_snapshot,
        )

        _store_barge_result(
            shared_state,
            result,
        )

        print(
            "Barge-in classified: "
            f"intent={result.decision.intent.value}, "
            f"reason={result.decision.reason}, "
            f"confidence={result.decision.confidence:.2f}, "
            f"transcript={result.transcript!r}"
        )

    except sd.PortAudioError as error:
        print(
            f"Barge-in audio error: {error}"
        )
        shared_state["barge_in_status"] = "error"

    except Exception as error:
        print(
            f"Barge-in listener failed: {error}"
        )
        shared_state["barge_in_status"] = "error"

        fallback = CapturedBargeIn(
            transcript="",
            decision=BargeInDecision(
                intent=BargeInIntent.UNCLEAR,
                reason="listener_error",
                confidence=0.0,
            ),
        )

        _store_barge_result(
            shared_state,
            fallback,
        )