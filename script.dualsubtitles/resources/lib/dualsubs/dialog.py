"""The "Subtitles" dialog during playback (F1): lists, D-pad only, every change applied live."""

import xbmcgui

from . import languages
from .session import NotPlaying, Session, Superseded, TrackError

LAYOUT_NAMES = {
    "stacked": "Both at the bottom, secondary above",
    "top-bottom": "Secondary on top, primary at the bottom",
    "primary-only": "Primary only",
}
STEPS = [("-1 s", -1000), ("-0.1 s", -100), ("+0.1 s", 100), ("+1 s", 1000)]


def seconds(ms):
    return "%+.1f s" % (ms / 1000.0)


class Dialog:
    def __init__(self, kodi):
        self.kodi = kodi
        self.ui = xbmcgui.Dialog()

    def run(self):
        try:
            session = Session.current(self.kodi)
        except NotPlaying:
            self.ui.ok("Dual subtitles", "Start a video first, then open this during playback.")
            return
        if not session.tracks:
            lines = ["This video has no subtitle tracks the add-on can find."] + session.warnings
            self.ui.ok("Dual subtitles", "[CR]".join(lines))
            return
        if not session.primary_key:
            session.choose()
        position = 0
        while True:
            entries = self._menu(session)
            choice = self.ui.select("Dual subtitles: " + session.describe(), [label for label, _ in entries],
                                    preselect=position)
            if choice < 0:
                return
            position = choice
            action = entries[choice][1]
            try:
                if action() is False:
                    return
            except NotPlaying:
                return
            except Superseded:
                session = Session.current(self.kodi)
            except TrackError as error:
                self.ui.ok("Dual subtitles", str(error))

    def _menu(self, session):
        primary, secondary = session.primary, session.secondary
        entries = []
        if not session.active and primary is not None:
            entries.append(("Show %s" % session.describe(), lambda: self._apply(session)))
        entries.append(("Primary: " + (primary.label() if primary else "none"),
                        lambda: self._pick(session, "primary")))
        entries.append(("Secondary: " + (secondary.label() if secondary else "none"),
                        lambda: self._pick(session, "secondary")))
        if primary is not None and secondary is not None:
            entries.append(("Swap primary and secondary", lambda: self._swap(session)))
        entries.append(("Layout: " + LAYOUT_NAMES.get(session.layout, session.layout),
                        lambda: self._layout(session)))
        if primary is not None:
            entries.append(("Primary timing: " + seconds(session.offsets.get(primary.key, 0)),
                            lambda: self._offset(session, primary)))
        if secondary is not None:
            entries.append(("Secondary timing: " + seconds(session.offsets.get(secondary.key, 0)),
                            lambda: self._offset(session, secondary)))
        if primary is not None and primary.styled:
            entries.append(("Primary styling: " + ("the file's own (signs, karaoke)" if session.keep_styling
                                                   else "plain dialogue in our style"),
                            lambda: self._toggle_styling(session)))
        entries.append(("Font size, colour, outline and margins…", lambda: self._settings(session)))
        for role, track in (("primary", primary), ("secondary", secondary)):
            if track is not None and track.external and track.path:
                entries.append(("Sync %s (%s) to the audio with Bazarr" % (role, languages.name(track.language)),
                                lambda track=track: self._sync(session, track)))
        if session.active:
            entries.append(("Turn dual subtitles off", lambda: self._off(session)))
        for warning in session.warnings + self._kodi_warnings():
            entries.append(("[COLOR grey]%s[/COLOR]" % warning, lambda: None))
        return entries

    def _kodi_warnings(self):
        try:
            override = self.kodi.json_rpc("Settings.GetSettingValue", {"setting": "subtitles.overridestyles"})
        except Exception:
            return []
        if override and override.get("value"):
            return ["Kodi's \"Override ASS/SSA styles\" setting is on: positions and colours will be Kodi's"]
        return []

    def _apply(self, session):
        progress = xbmcgui.DialogProgressBG()
        progress.create("Dual subtitles", "Loading subtitles")
        try:
            session.apply(progress=lambda message: progress.update(0, "Dual subtitles", message))
        finally:
            progress.close()

    def _pick(self, session, role):
        current = session.primary_key if role == "primary" else session.secondary_key
        other = session.secondary_key if role == "primary" else session.primary_key
        items, keys = [], []
        if role == "secondary":
            items.append("None")
            keys.append("")
        for track in session.tracks:
            label = track.label()
            if not track.usable:
                label = "[COLOR grey]%s (can't be used)[/COLOR]" % label
            elif track.key == other:
                label += " (the %s)" % ("secondary" if role == "primary" else "primary")
            items.append(label)
            keys.append(track.key)
        preselect = keys.index(current) if current in keys else 0
        choice = self.ui.select("%s track" % role.capitalize(), items, preselect=preselect)
        if choice < 0:
            return
        key = keys[choice]
        track = session.track(key)
        if track is not None and not track.usable:
            raise TrackError("%s: %s" % (track.label(), track.reason))
        previous = (session.primary_key, session.secondary_key)
        if role == "primary":
            if key == session.secondary_key:
                session.secondary_key = session.primary_key
            session.primary_key = key
        else:
            if key and key == session.primary_key:
                session.primary_key = session.secondary_key
            session.secondary_key = key
        if not session.primary_key:
            session.primary_key, session.secondary_key = session.secondary_key, ""
        try:
            self._apply(session)
        except TrackError:
            session.primary_key, session.secondary_key = previous
            raise

    def _swap(self, session):
        session.primary_key, session.secondary_key = session.secondary_key, session.primary_key
        self._apply(session)

    def _layout(self, session):
        keys = list(LAYOUT_NAMES)
        choice = self.ui.select("Layout", [LAYOUT_NAMES[k] for k in keys],
                                preselect=keys.index(session.layout) if session.layout in keys else 0)
        if choice >= 0:
            session.layout = keys[choice]
            self._apply(session)

    def _offset(self, session, track):
        """Live nudging (F3): every step is applied at once, the list stays open."""
        position = 2
        while True:
            offset = session.offsets.get(track.key, 0)
            items = ["Earlier by 1 s", "Earlier by 0.1 s", "Later by 0.1 s", "Later by 1 s", "Reset to 0"]
            choice = self.ui.select("%s: %s (later = shown later)" % (languages.name(track.language), seconds(offset)),
                                    items, preselect=position)
            if choice < 0:
                return
            position = choice
            session.offsets[track.key] = 0 if choice == 4 else offset + STEPS[choice][1]
            self._apply(session)

    def _toggle_styling(self, session):
        session.keep_styling = not session.keep_styling
        self._apply(session)

    def _settings(self, session):
        self.kodi.open_settings()
        self._apply(session)

    def _sync(self, session, track):
        progress = xbmcgui.DialogProgressBG()
        progress.create("Dual subtitles", "Bazarr is syncing %s to the audio (about a minute)" %
                        languages.name(track.language))
        try:
            session.sync(track)
        finally:
            progress.close()
        self._apply(session)
        self.kodi.notify("%s synced to the audio" % languages.name(track.language))

    def _off(self, session):
        session.off()
        return False
