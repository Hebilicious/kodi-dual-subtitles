import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "script.dualsubtitles", "resources", "lib"))
from dualsubs.jellyfin import Jellyfin, JellyfinError


def stream(index, external=False, path="", codec="subrip"):
    return {"Index": index, "Type": "Subtitle", "Language": "eng", "Codec": codec,
            "IsExternal": external, "Path": path}


class FakeJellyfin(Jellyfin):
    def __init__(self, streams):
        super().__init__("http://jellyfin.example", "key")
        self.streams = streams
        self.requested = []

    def _request(self, path, **kwargs):
        self.requested.append(path)
        if path.endswith("/PlaybackInfo"):
            return {"MediaSources": [{"Id": "src", "MediaStreams": self.streams}]}
        return b"text"


class PreparedFilesTest(unittest.TestCase):
    def test_embedded_tracks_can_never_be_fetched_even_with_old_saved_usable_flag(self):
        for codec in ("subrip", "ass", "ssa", "mov_text", "webvtt", "hdmv_pgs_subtitle"):
            server = FakeJellyfin([stream(2, codec=codec)])
            track = server.tracks({"Id": "item"})[0]
            self.assertFalse(track.usable)
            track.usable = True  # legacy session state must not bypass the load boundary
            with self.assertRaises(JellyfinError):
                server.fetch(track)
            self.assertEqual(server.requested, ["/Items/item/PlaybackInfo"])

    def test_external_container_is_not_a_prepared_file(self):
        server = FakeJellyfin([stream(0, True, "/media/movie.en.mks")])
        self.assertFalse(server.tracks({"Id": "item"})[0].usable)

    def test_external_file_is_served_in_native_format_after_index_moves(self):
        server = FakeJellyfin([stream(0, True, "/media/movie.en.srt")])
        track = server.tracks({"Id": "item"})[0]
        server.streams[0]["Index"] = 4
        self.assertEqual(server.fetch(track), (b"text", "srt"))
        self.assertEqual(server.requested[-1], "/Videos/item/src/Subtitles/4/0/Stream.srt")

    def test_live_metadata_must_still_identify_an_external_file(self):
        server = FakeJellyfin([stream(0, True, "/media/movie.en.srt")])
        track = server.tracks({"Id": "item"})[0]
        server.streams[0]["IsExternal"] = False
        with self.assertRaises(JellyfinError):
            server.fetch(track)
        self.assertTrue(all(p.endswith("PlaybackInfo") for p in server.requested))

    def test_styled_file_is_not_converted(self):
        server = FakeJellyfin([stream(0, True, "/media/movie.en.ass", "ass")])
        server.fetch(server.tracks({"Id": "item"})[0])
        self.assertTrue(server.requested[-1].endswith("Stream.ass"))
