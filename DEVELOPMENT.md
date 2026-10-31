Poteto STUDIO runs as static files; no build or dependency installation is needed
for the application. Serve the checkout with Python 3:

    python3 -m http.server 8001 --bind 127.0.0.1

Use the existing checkout for each isolated cloud task. Do not create a worktree
unless explicitly requested.

The studio accepts one UTF-8 HTML, CSS, JS, or TXT file at a time, up to 5 MiB.
Files are read locally; running, saving an app, and publishing are separate actions.
AI generation and image generation remain optional, with their original provider
configuration. OpenAI integration and multi-file/ZIP builds are not included.

Persistence behavior:

- `studio-state.js` saves the Create screen's input, unapplied code-editor changes,
  selected app ID, and the last ten versions locally after a short debounce and
  when leaving the screen/page. Restoring a draft fills the input; it never runs
  source code automatically. Cloud saving is explicit through Save app.
- Browser storage keys use `pt_v2_<kind>_user_<uid>` or `pt_v2_<kind>_guest`.
  Guest work stays on the device and is separate from signed-in accounts.
  Local browser storage is not encryption or a replacement for device security.
- The legacy `pt_apps` cache is retained. Only entries with the signing-in user's
  explicit UID are migrated. Unassigned legacy entries are not automatically
  exposed to a different account; retain the legacy cache for manual recovery.
- Private edits update the selected app ID. Cloud writes to the same ID are
  serialized. Failed writes retain the local copy and expose Retry save.
  Unsynced local entries are preserved when fetching newer cloud data.
- Save app updates My Gallery. Publishing/updating the public version is an
  explicit Publish / Share action. Existing public metadata is preserved on a
  private save. The fork password confirms a UI action; it is not copy protection.
- Account changes clear credentials, previews, chat state, and pending UI operations.
  Delayed asynchronous responses are discarded using an account revision guard.
  Loading apps never deletes user documents, including saved templates.
- If browser storage is unavailable/full, the editor remains usable and a visible
  error prompts the user to export HTML. Local drafts do not sync across devices.

Run regression tests from the repository root:

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

The tests require Python Playwright and Chromium (`/usr/bin/chromium` by default;
set `CHROMIUM_PATH` to override). They execute the actual UI with an in-memory
Firebase test double and do not send production writes. Production sign-in,
Firestore permissions, and public deployment require separate live validation.
