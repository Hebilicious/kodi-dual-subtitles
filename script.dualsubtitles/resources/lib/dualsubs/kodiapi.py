"""Everything the add-on asks of Kodi, in one place (the tests replace it with a fake)."""

import json
import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON_ID = "script.dualsubtitles"
STATUS_PROPERTY = "DualSubtitles.Status"  # JSON on the Home window, for agents (JSON-RPC XBMC.GetInfoLabels)


class Kodi:
    def __init__(self):
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.version = self.addon.getAddonInfo("version")
        self.addon_dir = xbmcvfs.translatePath(self.addon.getAddonInfo("path"))
        self.profile_dir = xbmcvfs.translatePath(self.addon.getAddonInfo("profile"))
        self.temp_dir = xbmcvfs.translatePath("special://temp/%s/" % ADDON_ID)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.profile_dir, exist_ok=True)
        self.player = xbmc.Player()

    # --- Settings ---------------------------------------------------------------------------

    def setting(self, key):
        return self.addon.getSetting(key)

    def setting_bool(self, key):
        return self.addon.getSetting(key) == "true"

    def open_settings(self):
        self.addon.openSettings()
        self.addon = xbmcaddon.Addon(ADDON_ID)  # reload what the viewer changed

    @property
    def device_id(self):
        return "kodi-dual-subtitles-" + (xbmc.getInfoLabel("Network.MacAddress").replace(":", "").lower() or "box")

    def string(self, string_id):
        return self.addon.getLocalizedString(string_id)

    # --- Player -----------------------------------------------------------------------------

    def playing_file(self):
        if not self.player.isPlayingVideo():
            return ""
        try:
            return self.player.getPlayingFile()
        except RuntimeError:
            return ""

    def video_info(self):
        """Show and title of the video playing, as Kodi knows them (library or Jellyfin add-on)."""
        try:
            tag = self.player.getVideoInfoTag()
            return {"show": tag.getTVShowTitle(), "title": tag.getTitle(), "season": tag.getSeason(),
                    "episode": tag.getEpisode()}
        except RuntimeError:
            return {}

    def load_subtitles(self, path):
        """Add the file as a subtitle stream, select it and show it; the video keeps playing."""
        self.player.setSubtitles(path)
        self.player.showSubtitles(True)

    def hide_subtitles(self):
        self.player.showSubtitles(False)

    # --- Files ------------------------------------------------------------------------------

    def listdir(self, folder):
        dirs, files = xbmcvfs.listdir(folder)
        return [d + "/" for d in dirs], files

    def read_file(self, path):
        handle = xbmcvfs.File(path)
        try:
            data = handle.readBytes()
        finally:
            handle.close()
        if not data and not xbmcvfs.exists(path):
            raise OSError("not found")
        return bytes(data)

    # --- Talking to the viewer and to agents ------------------------------------------------

    def log(self, message, level=xbmc.LOGINFO):
        xbmc.log("[%s] %s" % (ADDON_ID, message), level)

    def notify(self, message, seconds=4):
        xbmcgui.Dialog().notification("Dual subtitles", message, xbmcgui.NOTIFICATION_INFO,
                                      seconds * 1000)

    def set_status(self, status):
        xbmcgui.Window(10000).setProperty(STATUS_PROPERTY, json.dumps(status, ensure_ascii=False))

    def json_rpc(self, method, params=None):
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
        return response.get("result")
