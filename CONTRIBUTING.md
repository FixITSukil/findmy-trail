# Contributing to findmy-trail

Thanks for wanting to make this better! Bug fixes, features, and ideas are all
welcome.

## How to contribute

1. **Open an issue** first for anything non-trivial, so we can agree on the approach.
2. Fork → branch → make your change → open a Pull Request.
3. Keep PRs focused. Describe what changed and why.
4. **Never commit personal data** — no real `locations.json`, no IMEIs, no
   credentials, no tokens. The `.gitignore` guards the obvious ones; double-check
   your diff.

## Good first contributions

- Additional map layers / offline tiles
- Better hotspot / pattern algorithms
- Import from other sources (Google Timeline, GPX, KML)
- Accessibility and i18n
- Export formats (KML, GPX, PDF styling)

## Contributor License Agreement (please read)

This project is **source-available and non-commercial** (see `LICENSE.md`), and
the maintainer reserves commercial rights.

By submitting a contribution, **you agree that:**

1. You wrote it (or have the right to submit it), and
2. You **grant the project maintainer (copyright holder) a perpetual,
   worldwide, irrevocable, royalty-free license to use, modify, sublicense, and
   relicense your contribution — including as part of commercial or
   government-licensed versions of the software.**

In plain terms: you keep authorship credit, the community gets your improvement
for free under the non-commercial license, and the maintainer is able to include
it in commercial offerings. If you're not comfortable with that, please don't
submit code — but feel free to open issues and ideas.

## Code style

- Vanilla HTML/CSS/JS (no build step) for `tracker.html` / `report.html` — keep it
  dependency-light and self-contained.
- Python 3, standard library only where possible for `sync.py`.

Thanks! 🙌
