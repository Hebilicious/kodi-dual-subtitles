# Agent guide

Kodi add-on showing two subtitle tracks at once. See @README.md and @docs/requirements.md (F1–F11).

- Toolchain: proto pins moon and Python (`proto install`); moon runs everything.
- Before committing: `moon run dualsubs:check`. Rendering changes: `moon run dualsubs:verify` and look at the screenshots.
- Only `kodiapi.py`, `dialog.py`, `script.py` and `service.py` import Kodi modules; the rest stays unit-testable.
- No addresses, keys or paths of a particular setup in code, defaults or tests.
