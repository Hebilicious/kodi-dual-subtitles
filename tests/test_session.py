import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "script.dualsubtitles", "resources", "lib"))
from dualsubs.session import Session, TrackError
from dualsubs.tracks import Track
from dualsubs import work


class FakeKodi:
    def __init__(self, folder):
        self.temp_dir = self.profile_dir = folder

    def setting(self, name):
        return ""

    def setting_bool(self, name):
        return False


SRT = "1\n00:00:01,000 --> 00:00:02,000\n%s\n"


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.session = Session(FakeKodi(self.folder.name), "video.mkv")
        self.session.token = "playback-1"
        self.fetches = []
        self.served = "first"
        def fetch(track, progress):
            self.fetches.append(track.key)
            return SRT % self.served, "srt"
        self.session._fetch = fetch
        self.track = Track("file:movie.en.srt", "file", "en", "", "srt", True)

    def test_live_edits_reuse_files_and_do_not_mutate_cached_cues(self):
        first = self.session.load(self.track)
        first.cues[0].start = 9999
        first.cues[0].text = "changed"
        self.served = "second"
        self.assertEqual(self.session.load(self.track).cues[0].text, "first")
        self.assertEqual(self.session.load(self.track).cues[0].start, 1000)
        self.assertEqual(len(self.fetches), 1)

    def test_shared_cache_is_scoped_to_playback_or_explicit_refresh(self):
        self.session.load(self.track)
        other = Session(FakeKodi(self.folder.name), "video.mkv")
        other.token = self.session.token
        other._fetch = lambda *_: self.fail("same-session file was refetched")
        self.assertEqual(other.load(self.track).cues[0].text, "first")
        self.session.token = "playback-2"
        self.session._parsed.clear()
        self.served = "replacement"
        self.assertEqual(self.session.load(self.track).cues[0].text, "replacement")

    def test_legacy_embedded_selection_is_rejected_before_cache_or_fetch(self):
        self.track.external = False
        with self.assertRaises(TrackError):
            self.session.load(self.track)
        self.assertEqual(self.fetches, [])

    def test_slow_worker_cannot_extend_deadline(self):
        started = time.monotonic()
        with self.assertRaises(work.DeadlineError):
            work.run(lambda: time.sleep(0.3), seconds=0.02)
        self.assertLess(time.monotonic() - started, 0.2)

    def test_cancelled_worker_returns_without_waiting(self):
        with self.assertRaises(work.DeadlineError):
            work.run(lambda: time.sleep(0.3), cancelled=lambda: True)
