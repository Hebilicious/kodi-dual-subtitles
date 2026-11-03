# Agent guide

Kodi add-on showing two subtitle tracks at once. See @README.md and @docs/requirements.md (F1–F11).

- Toolchain: proto pins moon and Python (`proto install`); moon runs everything.
- Before committing: `moon run dualsubs:check`. Rendering changes: `moon run dualsubs:verify` and look at the screenshots.
- Only `kodiapi.py`, `dialog.py`, `script.py` and `service.py` import Kodi modules; the rest stays unit-testable.
- No addresses, keys or paths of a particular setup in code, defaults or tests.

## Merging

"Merge" means the work is on `main` both locally and on `origin`: merge and push, or, with a pull
request, merge it and pull. It is one step: never stop halfway, and never ask whether to do the
second half. `main` and `origin/main` are always the same commit, whoever moved them: check before
reporting a merge as done, and if you find them apart, sync them. A push refused because `origin`
moved: rebase and push again, never force-push. Other branches are pushed only when asked.
