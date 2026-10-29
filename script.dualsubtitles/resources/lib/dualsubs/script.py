"""The script entry point: the dialog for viewers, and parameters for agents (F9).

Agents call it through JSON-RPC after starting playback:

    {"method": "Addons.ExecuteAddon",
     "params": {"addonid": "script.dualsubtitles", "params": {"primary": "en", "secondary": "th"}}}

Parameters: ``primary`` and ``secondary`` (language codes or names; ``secondary=none`` for one
track), ``layout`` (stacked, the default; top-bottom; primary-only), ``action`` (``apply``, the default with
languages; ``off``; ``status``; ``sync`` with ``track=primary|secondary`` (Bazarr, F10);
``dialog``, the default without). The result goes to the Home
window property ``DualSubtitles.Status`` as JSON (read it with ``XBMC.GetInfoLabels``).
"""

import sys
import time

import xbmc

from . import assfile, languages
from .dialog import Dialog
from .kodiapi import Kodi
from .session import NotPlaying, Session, Superseded, TrackError

_WAIT_FOR_PLAYBACK = 60  # seconds an agent's call waits for the video it just started


def parse_args(argv):
    """Kodi passes JSON-RPC params as "key=value" arguments; a "?a=b&c=d" string works too."""
    args = {}
    for arg in argv:
        for part in arg.lstrip("?").split("&"):
            key, _, value = part.partition("=")
            if key:
                args[key.strip().lower()] = value.strip()
    return args


def run(argv):
    kodi = Kodi()
    args = parse_args(argv[1:])
    action = args.get("action") or ("apply" if ("primary" in args or "secondary" in args) else "dialog")
    if action == "dialog":
        Dialog(kodi).run()
    elif action == "apply":
        agent_apply(kodi, args)
    elif action == "off":
        try:
            Session.current(kodi).off()
        except NotPlaying:
            kodi.set_status({"state": "error", "message": "nothing is playing"})
    elif action == "sync":
        agent_sync(kodi, args.get("track", "secondary"))
    elif action == "status":
        try:
            kodi.set_status(Session.current(kodi).status())
        except NotPlaying:
            kodi.set_status({"state": "stopped"})
    else:
        kodi.set_status({"state": "error", "message": "unknown action %s" % action})


def agent_apply(kodi, args):
    kodi.set_status({"state": "working", "time": int(time.time())})
    monitor = xbmc.Monitor()
    deadline = time.time() + _WAIT_FOR_PLAYBACK
    while not kodi.playing_file() and time.time() < deadline and not monitor.abortRequested():
        monitor.waitForAbort(0.5)
    primary = languages.normalize(args.get("primary", ""))
    secondary_arg = args.get("secondary", "")
    secondary = "" if secondary_arg.lower() in ("", "none", "off") else languages.normalize(secondary_arg)
    layout = args.get("layout") if args.get("layout") in assfile.LAYOUTS else None
    try:
        session = Session.current(kodi)
        if args.get("primary") and not primary:
            raise TrackError("unknown language %s" % args["primary"])
        if secondary_arg and secondary_arg.lower() not in ("none", "off") and not secondary:
            raise TrackError("unknown language %s" % secondary_arg)
        if not session.choose(primary or None, secondary, layout):
            available = sorted({t.language for t in session.tracks if t.usable and t.language})
            raise TrackError("no %s track; this video has %s" % (
                languages.name(primary), ", ".join(available) or "no text subtitles"))
        if secondary and session.secondary is None:
            raise TrackError("no %s track besides the primary" % languages.name(secondary))
        session.apply(progress=kodi.notify)
        kodi.notify(session.describe())
    except NotPlaying:
        kodi.set_status({"state": "error", "message": "nothing is playing"})
    except (TrackError, Superseded) as error:
        kodi.log(str(error), xbmc.LOGWARNING)
        kodi.set_status({"state": "error", "message": str(error), "time": int(time.time())})


def agent_sync(kodi, role):
    """Have Bazarr re-sync the primary or secondary track to the audio, then reload it (F10)."""
    kodi.set_status({"state": "working", "time": int(time.time())})
    try:
        session = Session.current(kodi)
        track = session.primary if role == "primary" else session.secondary
        if track is None:
            raise TrackError("no %s track is shown" % role)
        session.sync(track)
        session.apply()
        status = session.status()
        status["state"] = "synced"
        kodi.set_status(status)
    except NotPlaying:
        kodi.set_status({"state": "error", "message": "nothing is playing"})
    except (TrackError, Superseded) as error:
        kodi.log(str(error), xbmc.LOGWARNING)
        kodi.set_status({"state": "error", "message": str(error), "time": int(time.time())})


def main():
    run(sys.argv)
