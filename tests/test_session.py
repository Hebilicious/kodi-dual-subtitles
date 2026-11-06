import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "script.dualsubtitles", "resources", "lib"))

from dualsubs.session import Session  # noqa: E402
from dualsubs.tracks import Track  # noqa: E402


class FakeKodi:
    def __init__(self, folder):
        self.temp_dir = folder
        self.profile_dir = folder

    def setting(self, _name):
        return ""

    def setting_bool(self, _name):
        return False


SRT = "1\n00:00:01,000 --> 00:00:02,000\n%s\n"


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.session = Session(FakeKodi(self.folder), "video.mkv")
        self.served = {}
        self.session._fetch = lambda track, progress: (SRT % self.served[track.key], "srt")

    def text(self, track):
        return self.session.load(track).cues[0].text

    def test_a_replaced_subtitle_file_is_shown_as_it_is_now(self):
        thai = Track(key="jellyfin:2", source="jellyfin", language="th", title="", codec="subrip", external=True)
        self.served["jellyfin:2"] = "old"
        self.assertEqual(self.text(thai), "old")
        self.served["jellyfin:2"] = "new"
        self.assertEqual(self.text(thai), "new")

    def test_a_track_extracted_from_the_video_is_fetched_once(self):
        english = Track(key="jellyfin:5", source="jellyfin", language="en", title="", codec="subrip", external=False)
        self.served["jellyfin:5"] = "first"
        self.assertEqual(self.text(english), "first")
        self.served["jellyfin:5"] = "second"
        self.assertEqual(self.text(english), "first")


if __name__ == "__main__":
    unittest.main()
