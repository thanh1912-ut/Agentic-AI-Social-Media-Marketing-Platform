# UI refresh — verification and rollback

## Scope

This change refreshes the Next.js frontend layout and styling: shared app shell,
responsive navigation, auth pages, workspace pages, reusable UI components,
local Satoshi fonts, and mock fixtures used by frontend tests. It does not change
the API, database, workers, credentials, DeepSeek configuration, or Meta publishing.
Satoshi is used as an unmodified local UI webfont; Fontshare identifies the family
as covered by the ITF Free Font License ([family and license](https://www.fontshare.com/fonts/satoshi)).

## Verification

| Check | Result | Notes |
|---|---|---|
| ESLint | PASS | `npm run lint` |
| TypeScript | PASS | `npx tsc --noEmit --incremental false`; the standard typecheck first hit a sandbox write restriction for `tsconfig.tsbuildinfo`, not a code diagnostic. |
| Frontend unit tests | PASS | 48 tests across 4 files. |
| Full browser E2E | PASS | 48 passed, 2 screenshot cases skipped because the capture flag was not set. The test suite exercises the current demo/mock flows. |
| Final responsive/navigation E2E | PASS | 8 passed after the final header adjustment, across desktop and mobile Chromium. |
| Production build | PASS | Next.js production build completed as the E2E web server startup step. |
| Viewport overflow | PASS | Documents, Fanpages, and Analytics checked at 390, 768, 1024, and 1440 CSS pixels. |
| Mobile navigation | PASS | Opens as a dialog, closes with Escape, and returns focus to its opener. |
| Screenshots | PASS | Captured from the demo build; see the files below. |
| Real authentication/API | NOT RUN | At verification time, the previously used API at `127.0.0.1:8001` and preview at `127.0.0.1:13104` refused connections. No real login, database, DeepSeek, or Meta request was made. |

The browser tests use mock data and visibly label the workspace as a demo. They
verify frontend behavior only; they do not prove real API persistence or real
authentication. No public Facebook post was sent and no extra DeepSeek call was
made for this UI work.

## Visual review

- Desktop: [desktop.png](./desktop.png)
- Mobile: [mobile.png](./mobile.png)

Both captures show the demo banner so sample metrics cannot be mistaken for live
workspace data. The mock dashboard copy now reflects user-authored brand
profiles and the supported document formats.

## Preview and rollback

The existing preview at port `13104` was left untouched. A standalone preview,
if started from this worktree, is demo-only and must not be used as a real login.

To roll back this feature branch after it has been integrated, revert the UI
refresh commit. This change does not require a database rollback. Keep the
previous preview/build available until the real backend has been verified with
the refreshed frontend.
