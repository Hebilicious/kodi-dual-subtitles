# Agent guide

A Kodi add-on (`script.dualsubtitles`) that shows two subtitle tracks at once. Read
[README.md](README.md) for what it does and how it works, and
[docs/requirements.md](docs/requirements.md) for the requirements the code refers to (F1 to F11).

## Toolchain

proto pins moon and Python in `.prototools`, and moon runs the tasks. Don't install them any
other way.

```sh
proto install                 # pinned moon and Python
moon run dualsubs:check       # must pass before committing
moon run dualsubs:build       # the installable zip in dist/
moon run dualsubs:verify      # the add-on in a real Kodi, headless (needs kodi, Xvfb, ffmpeg)
```

## Rules

- The add-on is pure Python with no dependencies outside Kodi, so one zip installs everywhere.
  Code outside `kodiapi.py`, `dialog.py`, `script.py` and `service.py` must not import Kodi
  modules: it is what the unit tests cover.
- A change in rendering is checked in a real Kodi (`verify.sh`) and its screenshots, not only in
  unit tests.
- Fonts and the dictionary are downloaded by `build.sh` at pinned versions with checksums; don't
  commit them.
- No addresses, keys or paths of a particular setup in the code, the defaults or the tests: they
  come from the add-on's settings or from environment variables.
