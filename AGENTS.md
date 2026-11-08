# Agent guide

Kodi add-on showing two subtitle tracks at once. See @README.md and @docs/requirements.md (F1–F11).

- Toolchain: proto pins moon and Python (`proto install`); moon runs everything.
- Before committing: `moon run dualsubs:check`. Rendering changes: `moon run dualsubs:verify` and look at the screenshots.
- Only `kodiapi.py`, `dialog.py`, `script.py` and `service.py` import Kodi modules; the rest stays unit-testable.
- No addresses, keys or paths of a particular setup in code, defaults or tests.

## Playback boundary

Only existing independent text subtitle files may be loaded. Never fetch an embedded stream,
including from a warm extraction cache or legacy saved session. No playback action may trigger
extraction, searches or audio alignment. Missing files fail promptly and leave the working pair
untouched. Timing/layout changes reuse loaded cues without source requests.

## Where changes come from

This repository is published from a private monorepo, and its commits are generated. A change made
directly here stops the next publish, so pull requests are ported by a maintainer, not merged. In
the monorepo, a commit that changes this project says what the public may read in a
`<public>...</public>` section of its message; nothing else in the message leaves.
