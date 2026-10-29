import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "script.dualsubtitles", "resources", "lib"))

from dualsubs import assfile, languages, subtitles, thai, wrap  # noqa: E402


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), "rb") as handle:
        return handle.read()


class ParseTest(unittest.TestCase):
    def test_srt_keeps_italics_and_breaks(self):
        sub = subtitles.parse(subtitles.decode(fixture("plain.en.srt")))
        self.assertEqual(sub.format, "srt")
        self.assertEqual(len(sub.cues), 2)
        self.assertEqual(sub.cues[0].start, 2000)
        self.assertEqual(sub.cues[0].text, "{\\i1}Hello{\\i0}, Frieren.")
        self.assertIn("\\N", sub.cues[1].text)

    def test_srt_without_blank_lines_and_with_dots(self):
        text = "1\n00:00:01.5 --> 00:00:02,000\nOne\n2\n00:00:03,000 --> 00:00:04,000\nTwo\n"
        sub = subtitles.parse(text)
        self.assertEqual([c.text for c in sub.cues], ["One", "Two"])
        self.assertEqual(sub.cues[0].start, 1500)

    def test_vtt(self):
        text = "WEBVTT\n\nNOTE a note\n\n00:01.000 --> 00:02.000 line:0\n<v Bob>Hi <c.yellow>there</c>\n"
        sub = subtitles.parse(text)
        self.assertEqual(sub.format, "vtt")
        self.assertEqual(sub.cues[0].text, "Hi there")

    def test_ass_styles_and_events(self):
        sub = subtitles.parse(subtitles.decode(fixture("styled.ja.ass")))
        self.assertEqual(sub.format, "ass")
        self.assertEqual([s["Name"] for s in sub.styles], ["Default", "Sign"])
        self.assertEqual(sub.info["PlayResY"], "360")
        self.assertTrue(sub.styled)
        self.assertEqual(sub.cues[1].start, 2000)

    def test_flattening_drops_signs_and_keeps_italics(self):
        sub = subtitles.parse(subtitles.decode(fixture("styled.ja.ass")))
        cues = subtitles.plain_cues(sub)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].text, "{\\i1}こんにちは{\\i0}、フリーレン。")

    def test_flattening_merges_layered_copies(self):
        text = ("[Script Info]\nPlayResY: 360\n[V4+ Styles]\nFormat: Name, Fontsize\nStyle: Default,20\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                "Dialogue: 1,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\bord4}Hi\n"
                "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\bord0}Hi\n")
        self.assertEqual([c.text for c in subtitles.plain_cues(subtitles.parse(text))], ["Hi"])

    def test_decode_legacy_thai(self):
        self.assertEqual(subtitles.decode("สวัสดี".encode("cp874"), "th"), "สวัสดี")
        self.assertEqual(subtitles.decode("﻿hello".encode("utf-8")), "hello")

    def test_empty_file(self):
        with self.assertRaises(subtitles.SubtitleError):
            subtitles.parse("nothing here")


class LanguageTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(languages.normalize("tha"), "th")
        self.assertEqual(languages.normalize("Thai"), "th")
        self.assertEqual(languages.normalize("th-TH"), "th")
        self.assertEqual(languages.normalize("ger"), "de")
        self.assertEqual(languages.normalize("pt-BR"), "pt")
        self.assertEqual(languages.normalize("xx"), "")
        self.assertEqual(languages.parse_list("Thai, en; jpn"), ["th", "en", "ja"])


class ThaiTest(unittest.TestCase):
    WORDS = {"ออก", "จะ", "โง่", "ไป", "หน่อย", "นะ", "เดิน", "ทาง", "คน", "เดียว"}

    def test_dictionary_words(self):
        self.assertEqual(thai.segment("ออกจะโง่ไปหน่อยนะ", self.WORDS), ["ออก", "จะ", "โง่", "ไป", "หน่อย", "นะ"])

    def test_unknown_words_never_split_a_cluster(self):
        for piece in thai.segment("เดินทางสเกลสคนเดียว", self.WORDS):
            self.assertFalse(thai._is_mark(piece[0]), piece)
            self.assertNotIn(piece[-1], "เแโใไ")

    def test_shipped_dictionary_when_built(self):
        words = thai.load_words()
        if not words:
            self.skipTest("thaidict.txt is added by build.sh")
        self.assertIn("ภาษา", words)


class WrapTest(unittest.TestCase):
    def test_latin_is_left_to_libass(self):
        line = "word " * 40
        self.assertEqual(wrap.wrap(line, 10), line)

    def test_thai_wraps_between_words(self):
        thai_words = ThaiTest.WORDS
        line = "ออกจะโง่ไปหน่อยนะ" * 4
        original = thai._words
        thai._words = thai_words
        try:
            wrapped = wrap.wrap(line, 12)
        finally:
            thai._words = original
        parts = wrapped.split("\\N")
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), line)
        for part in parts:
            self.assertLessEqual(wrap.text_width(part), 12)

    def test_japanese_keeps_okurigana_and_punctuation(self):
        wrapped = wrap.wrap("千年以上生きてきたエルフにとって、人間の一生はあまりにも短い。それでも私は、彼らのことを知りたい。", 30)
        for part in wrapped.split("\\N"):
            self.assertFalse(part.startswith(("い", "、", "。")), wrapped)
            self.assertLessEqual(wrap.text_width(part), 30)

    def test_tags_stay_attached(self):
        wrapped = wrap.wrap("{\\i1}" + "あ" * 40 + "{\\i0}", 15)
        self.assertTrue(wrapped.startswith("{\\i1}"))
        self.assertTrue(wrapped.endswith("{\\i0}"))


class AssFileTest(unittest.TestCase):
    def setUp(self):
        self.en = subtitles.parse(subtitles.decode(fixture("plain.en.srt")))
        self.th = subtitles.parse(subtitles.decode(fixture("long.th.srt"), "th"))
        self.ja = subtitles.parse(subtitles.decode(fixture("styled.ja.ass")))

    def events(self, text):
        return [line for line in text.splitlines() if line.startswith("Dialogue:")]

    def test_top_bottom_with_offsets(self):
        text = assfile.build(assfile.Layer(self.en, assfile.TrackStyle()),
                             assfile.Layer(self.th, assfile.TrackStyle(font="Noto Sans Thai"), offset=-1500),
                             layout="top-bottom")
        self.assertIn("Style: Primary,Noto Sans,56,&H00BFBFBF", text)
        self.assertIn(",8,", [l for l in text.splitlines() if l.startswith("Style: Secondary")][0])
        events = self.events(text)
        self.assertIn("Dialogue: 0,0:00:02.00,0:00:09.00,Primary,", events[1])
        self.assertIn("Dialogue: 1,0:00:00.50,0:00:07.50,Secondary,", events[0])

    def test_default_is_both_at_the_bottom(self):
        text = assfile.build(assfile.Layer(self.en, assfile.TrackStyle()), assfile.Layer(self.th, assfile.TrackStyle()))
        secondary_style = [l for l in text.splitlines() if l.startswith("Style: Secondary")][0]
        self.assertEqual(secondary_style.split(",")[18], "2")  # Alignment: bottom centre

    def test_offset_drops_cues_before_zero(self):
        text = assfile.build(assfile.Layer(self.en, assfile.TrackStyle(), offset=-9500))
        self.assertEqual(len(self.events(text)), 1)

    def test_stacked_puts_secondary_above_primary_lines(self):
        text = assfile.build(assfile.Layer(self.en, assfile.TrackStyle()),
                             assfile.Layer(self.th, assfile.TrackStyle()), layout="stacked")
        secondary = [e for e in self.events(text) if ",Secondary," in e]
        one_line = int(secondary[0].split(",")[7])
        two_lines = int(secondary[1].split(",")[7])
        self.assertGreater(one_line, 50)
        self.assertGreater(two_lines, one_line)

    def test_primary_only(self):
        text = assfile.build(assfile.Layer(self.en, assfile.TrackStyle()),
                             assfile.Layer(self.th, assfile.TrackStyle()), layout="primary-only")
        self.assertNotIn("Style: Secondary", text)

    def test_kept_styling_uses_source_resolution(self):
        text = assfile.build(assfile.Layer(self.ja, assfile.TrackStyle(), keep_styling=True),
                             assfile.Layer(self.en, assfile.TrackStyle(size=54)))
        self.assertIn("PlayResY: 360", text)
        self.assertIn("Style: P-Sign,", text)
        self.assertIn("Style: Secondary,Noto Sans,18,", text)  # 54 px at 1080 lines = 18 at 360
        self.assertIn("{\\pos(40,40)}", text)
        long_line = [e for e in self.events(text) if "千年" in e][0]
        self.assertIn("\\N", long_line)

    def test_two_hour_film_is_fast(self):
        cues = [subtitles.Cue(i * 4000, i * 4000 + 3000, "สำหรับเอลฟ์ที่มีชีวิตอยู่มานานกว่าพันปีชีวิตของมนุษย์") for i in range(1800)]
        th = subtitles.Subtitle("srt", cues)
        en = subtitles.Subtitle("srt", [subtitles.Cue(c.start, c.end, "A line of English dialogue, quite long.")
                                        for c in cues])
        started = time.perf_counter()
        assfile.build(assfile.Layer(en, assfile.TrackStyle()), assfile.Layer(th, assfile.TrackStyle()), "stacked")
        elapsed = time.perf_counter() - started
        # The target is 300 ms on a low-end TV box, several times slower than a desktop.
        print("\n2-hour film: %d ms" % (elapsed * 1000))
        self.assertLess(elapsed, 0.3, elapsed)


if __name__ == "__main__":
    unittest.main()
