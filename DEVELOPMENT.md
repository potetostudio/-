Poteto STUDIO runs as static files; no build or dependency installation is needed
for the application. Serve the checkout with Python 3:

    python3 -m http.server 8001 --bind 127.0.0.1

Use the existing checkout for each isolated cloud task. Do not create a worktree
unless explicitly requested.

The studio accepts one UTF-8 HTML, CSS, JS, or TXT file at a time, up to 5 MiB.
Files are read locally; running, saving an app, and publishing are separate actions.
AI generation and image generation remain optional, with their original provider
configuration. OpenAI integration and multi-file/ZIP builds are not included.
The Create input's Clear all code button empties the input in one click, cancels
pending file reads, and persists an empty recovery state. It resets the imported
file type/title and edit target so replacement code starts a new app; saved gallery
apps and their per-app work records are retained.
Undo restores the cleared input, filename/type, title, edit target, and history
without executing code. The undo snapshot is memory-only and is discarded on
new input/import, entering another screen's editor, or changing accounts. Repeated
clears of an already empty input keep the original undo snapshot.

Persistence behavior:

- `studio-state.js` saves the Create screen's input, unapplied code-editor changes,
  selected app ID, and recent history after a short debounce and when leaving.
  Create restores the latest input without running it. My Gallery's Edit opens
  that app's saved work, including unapplied changes, even after editing other
  apps or reloading. There is no separate Resume draft button. Unmodified local
  snapshots yield to updated saved code; pending edits are retained.
- `local-store.js` uses IndexedDB (`poteto-studio-local-v1`, `records`) for code,
  gallery caches, profiles, and work records. Legacy localStorage records are
  migrated only after a successful durable write. If IndexedDB is unavailable,
  localStorage is the fallback. The UI reports saved only after a store commits.
  History keeps up to ten versions within a 256 Ki-character historical-code
  budget, deduplicates consecutive snapshots, and references the current code
  instead of copying it. The current code itself is never truncated.
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
- The authentication callback opens/closes the login gate immediately and shows
  the gallery on sign-in. Local work hydration, shared-link fetches, and chat
  subscription setup cannot keep the login overlay open. Local hydration still
  precedes cloud-cache merging to retain unsynced edits. Shared links that finish
  after a user navigates away cannot replace that screen. Local script URLs use
  a release query; bump all four together when deploying related script changes.
- If both stores are unavailable/full, the editor and gallery navigation remain
  usable. Memory preserves work within the page, and a visible error prompts
  HTML export before closing. Guest saves do not report success in this case.
  Automatic saves stay on this browser; cloud saving is explicit via Save app.

Run regression tests from the repository root:

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

The tests require Python Playwright and Chromium (`/usr/bin/chromium` by default;
set `CHROMIUM_PATH` to override). They execute the actual UI with an in-memory
Firebase test double and do not send production writes. Production sign-in,
Firestore permissions, and public deployment require separate live validation.

Gallery behavior:

- My Gallery supports Recently updated, Recently created, and Name ordering.
  Pinned matching cards always appear first. Search still filters pinned cards.
  Sort and pins use the account-scoped `gallery` record in local browser storage;
  they do not modify app timestamps, likes, public records, or array order.
  Private saves retain the original creation timestamp in cloud records. Older
  records without one fall back to their saved timestamp for creation ordering.
- Duplicate copies the saved gallery code into a new independently identified
  private app, with a unique copy name, fresh timestamps, zero likes, and no pin.
  It stays in the gallery and never overwrites the source or republishes it.
  Signed-in copies use the existing private cloud save/retry path; guest copies
  stay local. Failed cloud writes retain the same local copy for retry. Concurrent
  clicks for one source share an operation guard, and account changes cancel UI
  completion. Pending editor changes are separate from the saved source copied.
- New work uses its HTML title, imported filename, or first heading as its name.
  Explicit names are retained. Legacy Pasted code/Saved app names are improved
  in the local cache; remote records change only on an explicit save/rename.
- Gallery thumbnails are generated by `gallery-ui.js` in isolated iframes, up to
  three at once, only for visible cards. Rendering is converted to script-free
  SVG posters (including clean Canvas images); the iframe is then removed.
  A bounded in-memory cache is scoped to the account and invalidated by code
  changes. Posters are never added to Firestore or browser persistent storage.
- Private thumbnails can run inline app scripts without parent/storage/API-key
  access. Public thumbnails omit app scripts and event handlers. Thumbnail CSP
  disables network dependencies. External services/assets and some browser
  features may therefore look different from the fully opened app. Failed
  captures show an Open to view the app fallback.
- The editor's back button, including its fullscreen variant, returns directly
  to the gallery even if persistent storage fails. Automatic work snapshots do
  not silently overwrite the gallery app or its public version. Returning to
  Create restores the input; Edit recovers each app's pending work.

Playback preservation:

- Opening a gallery app creates a fresh, equally sandboxed iframe after making
  the app view visible. This avoids a valid but non-rendering document retained
  by a previously hidden srcdoc frame. Old playback requests remain guarded by
  the account revision and preview sequence.
- Gallery playback never splits source at a doctype or inserts scripts at a
  closing body tag: those strings can occur inside normal app JavaScript.
  A header-only lexical scan places trusted instrumentation without serializing
  the application or changing its original head attributes/standards mode.
- Legacy editor wrappers are unwrapped only when an actual code-area textarea,
  game-frame iframe, and launcher script are present. Encoded textarea HTML is
  decoded through its value. Other documents are preserved as supplied.
- Runtime errors and empty saved code produce a visible playback message with
  Retry/Close controls. Messages are accepted only from the current iframe and
  playback token. Public playback still receives no viewer API key and has no
  same-origin privileges.
