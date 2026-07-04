"""Shared microphone lock for Avens.

Only one sounddevice input stream may own the microphone at a time.
This prevents wake-word listening, speech recording, and barge-in detection
from racing each other on Windows audio drivers.
"""

import threading

microphone_lock = threading.RLock()
