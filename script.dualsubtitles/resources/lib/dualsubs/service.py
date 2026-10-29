"""The background service: installs the fonts and the key, and applies remembered choices when a
video starts (F5)."""

import os
import shutil

import xbmc
import xbmcvfs

from .kodiapi import ADDON_ID, Kodi
from .session import NotPlaying, Session, Superseded, TrackError

FONTS_DIR = "special://home/media/Fonts/"
KEYMAP = "special://profile/keymaps/%s.xml" % ADDON_ID
# Long press of the keys that already deal with subtitles or menus during playback.
KEYMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Written by the Dual subtitles add-on (setting "Open with a long press"); removed when that is off. -->
<keymap>
  <FullscreenVideo>
    <keyboard>
      <l mod="longpress">RunScript(%(id)s)</l>
      <c mod="longpress">RunScript(%(id)s)</c>
      <menu mod="longpress">RunScript(%(id)s)</menu>
    </keyboard>
    <remote>
      <subtitle mod="longpress">RunScript(%(id)s)</subtitle>
      <menu mod="longpress">RunScript(%(id)s)</menu>
    </remote>
  </FullscreenVideo>
</keymap>
""" % {"id": ADDON_ID}


def install_fonts(kodi):
    """Copy the add-on's fonts where Kodi's libass looks for them (F7); not the skin's or the OS's."""
    source = os.path.join(kodi.addon_dir, "resources", "fonts")
    target = xbmcvfs.translatePath(FONTS_DIR)
    if not os.path.isdir(source):
        kodi.log("no fonts in the add-on; Thai and Japanese fall back to Kodi's fonts", xbmc.LOGWARNING)
        return
    os.makedirs(target, exist_ok=True)
    for name in os.listdir(source):
        if not name.lower().endswith((".ttf", ".otf")):
            continue
        src, dst = os.path.join(source, name), os.path.join(target, name)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
            kodi.log("installed font " + name)


def install_keymap(kodi):
    """Write or remove the keymap; returns whether it changed and Kodi must reload its keymaps."""
    path = xbmcvfs.translatePath(KEYMAP)
    wanted = KEYMAP_XML if kodi.setting_bool("long_press") else None
    current = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    if current == wanted:
        return False
    if wanted is None:
        os.remove(path)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(wanted)
    reload_keymaps(kodi)
    return True


def reload_keymaps(kodi):
    # Through JSON-RPC: a builtin sent while Kodi starts up, or to a modal dialog, gets dropped.
    kodi.json_rpc("Input.ExecuteAction", {"action": "reloadkeymaps"})


def auto_apply(kodi):
    """Show the remembered or default pair for the video that just started, if its tracks match."""
    if not kodi.setting_bool("auto_apply"):
        return
    try:
        session = Session.current(kodi, rediscover=True)
        session.save_state()
        if not session.choose():
            kodi.log("no subtitle track matches the preferences for %s" % session.title)
            kodi.set_status(session.status())
            return
        session.apply(progress=kodi.notify)
        kodi.notify(session.describe())
    except (NotPlaying, Superseded) as reason:
        kodi.log("not applied: %s" % reason)
    except TrackError as error:
        kodi.log(str(error), xbmc.LOGWARNING)
        kodi.notify(str(error), seconds=8)


class Player(xbmc.Player):
    def __init__(self, service):
        super().__init__()
        self.service = service

    def onAVStarted(self):
        if self.isPlayingVideo():
            kodi = self.service.kodi()
            if self.service.keymap_pending:
                reload_keymaps(kodi)  # once more, in case the one at startup was dropped
                self.service.keymap_pending = False
            auto_apply(kodi)

    def onPlayBackStopped(self):
        self.service.kodi().set_status({"state": "stopped"})

    def onPlayBackEnded(self):
        self.service.kodi().set_status({"state": "stopped"})


class Monitor(xbmc.Monitor):
    def __init__(self, service):
        super().__init__()
        self.service = service

    def onSettingsChanged(self):
        kodi = self.service.kodi()
        install_keymap(kodi)


class Service:
    keymap_pending = False

    def kodi(self):
        return Kodi()  # fresh, so changed settings are read

    def run(self):
        kodi = self.kodi()
        install_fonts(kodi)
        self.keymap_pending = install_keymap(kodi)
        kodi.set_status({"state": "idle"})
        monitor = Monitor(self)
        player = Player(self)
        kodi.log("service started, version %s" % kodi.version)
        monitor.waitForAbort()
        del player
