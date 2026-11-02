import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "script.dualsubtitles", "resources", "lib"))

from dualsubs.jellyfin import Jellyfin  # noqa: E402


def stream(index, language, title, external=False, path=""):
    return {"Index": index, "Type": "Subtitle", "Language": language, "Title": title, "Codec": "ass",
            "IsExternal": external, "Path": path}


EMBEDDED = [{"Index": 0, "Type": "Video"}, {"Index": 1, "Type": "Audio", "Language": "jpn"},
            stream(2, "eng", "English"), stream(3, "ind", "Indonesian"), stream(4, "tha", "Thai")]
# Jellyfin numbers external subtitles first: a file Bazarr adds moves every embedded track by one.
WITH_FILE = [stream(0, "tha", None, external=True, path="/tv/Show/S01E01.th.srt")] + \
    [dict(s, Index=s["Index"] + 1) for s in EMBEDDED]


class FakeJellyfin(Jellyfin):
    def __init__(self, streams):
        super().__init__("http://jellyfin.example", "key")
        self.streams = streams
        self.requested = []

    def _request(self, path, query=None, timeout=None, raw=False, method="GET"):
        self.requested.append(path)
        if path.endswith("/PlaybackInfo"):
            return {"MediaSources": [{"Id": "src", "MediaStreams": self.streams}]}
        return b"text"


class TrackIndexTest(unittest.TestCase):
    def test_fetch_follows_a_track_whose_index_moved(self):
        server = FakeJellyfin(EMBEDDED)
        thai = [t for t in server.tracks({"Id": "item"}) if t.language == "th"][0]
        server.streams = WITH_FILE
        server.fetch(thai)
        self.assertEqual(server.requested[-1], "/Videos/item/src/Subtitles/5/0/Stream.ass")

    def test_keys_do_not_depend_on_indexes(self):
        before = {t.key for t in FakeJellyfin(EMBEDDED).tracks({"Id": "item"})}
        after = {t.key for t in FakeJellyfin(WITH_FILE).tracks({"Id": "item"})}
        self.assertTrue(before < after)


if __name__ == "__main__":
    unittest.main()
