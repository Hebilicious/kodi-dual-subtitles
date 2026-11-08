"""Bound blocking subtitle reads without letting late workers change the player."""

import queue
import threading
import time

SECONDS = 3.0
MAX_BYTES = 8 * 1024 * 1024


class DeadlineError(Exception):
    pass


def run(function, cancelled=None, seconds=SECONDS):
    """Only return a worker's value before the deadline; the caller alone commits player state."""
    result = queue.Queue(maxsize=1)

    def worker():
        try:
            result.put((True, function()))
        except Exception as error:
            result.put((False, error))

    threading.Thread(target=worker, daemon=True).start()
    deadline = time.monotonic() + seconds
    while True:
        if cancelled and cancelled():
            raise DeadlineError("subtitle loading cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeadlineError("subtitle files are not ready: loading exceeded 3 seconds")
        try:
            success, value = result.get(timeout=min(0.05, remaining))
        except queue.Empty:
            continue
        if success:
            return value
        raise value
