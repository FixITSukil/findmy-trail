# Security & Privacy Policy

## Reporting a vulnerability

Please **do not** open a public issue for security or privacy problems.
Instead, report privately via
[GitHub Security Advisories](https://github.com/FixITSukil/findmy-trail/security/advisories/new).

We'll aim to acknowledge within a few days.

## What counts

Because this tool handles location data and credentials, we especially want to hear about:

- Any path where a **token, Apple ID, or location data** could leak (e.g. accidentally committed, exposed in logs, or sent to a third party)
- Cross-site scripting or injection in `tracker.html` / `report.html`
- The cloud-sync flow exposing data to anyone without the token

## For users — protect yourself

- **Never commit your real `locations.json`** or a screenshot showing real locations.
- Keep your GitHub sync token in `.icloud_session/` (gitignored) — never paste it into chat, issues, or commits.
- Use a **private** repo for your own location data; only the code should be public.
- Change the default `CONFIG.pin` before hosting the tracker anywhere public.

## Ethical use

This project is for locating devices you **own or are authorised to locate**.
Using it to track a person without their consent may be illegal. Reports of the
project being used for stalking/abuse are taken seriously.
