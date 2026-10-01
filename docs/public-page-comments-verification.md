# Public Page comments — verification

Kết quả bổ sung 2026-10-01 14:43 Asia/Ho_Chi_Minh: suppression/restore/browser đã đạt trên dữ liệu tổng hợp. Xem [verification mới nhất](page-workspace-research-verification.md) cho test IDs và phạm vi; rollout migration0029 đã đạt, code `c221b01cd38b129f29650fe5edd8608cf8dde0d6`/release `codex-page-workspaces-research-b96e785ffe5d-20261001T074846Z`.


Timestamp: 2026-10-01 04:48 Asia/Ho_Chi_Minh.
Branch: `codex/page-workspaces-research`; baseline `1b29ab4c99872246fa44565a70345f9762039af3`.
Tested implementation and deployed code: `9197847d7915ec2520feca417c8d33fb30b659b1`. Remote implementation SHA verified after push.

## Results

| Check | Result | Evidence / limits |
|---|---|---|
| Relevant Python regression | PASS, synthetic | 180 passed in 15.41s on the isolated checkout. Unit/API transaction fixtures are not substituted for PostgreSQL acceptance. |
| Frontend unit tests | PASS, fixtures | 6 files / 56 tests, including Owner restriction, distinct likes/reactions, unknown authors, expiry, hide/revoke cache eviction and current policy revision |
| Backend Ruff | PASS | Changed Python source and tests; --no-cache |
| Frontend lint and typecheck | PASS | Manifest commands; typecheck rerun with filesystem approval after the sandbox denied its incremental cache write |
| OpenAPI and generated TypeScript | PASS | Repository export/generation scripts; OpenAPI --check passed |
| Production frontend build | PASS | Real build with mocks off/API 8001; separate test build used API 18011 |
| Full Go tests and build | PASS | `go test ./...` and `go build`; includes owned loopback/TLS transport fixtures, not just Python mocks |
| PostgreSQL public comments | PASS, synthetic | 2 tests: concurrent replay/history/fencing, plus actual runner subprocess -> Redis -> Celery -> PostgreSQL and duplicate delivery |
| PostgreSQL existing comment quarantine/checkpoints | PASS, synthetic | 5 tests initially passed; Redis scenario was initially skipped then rerun with its explicit disposable Redis URL and passed. Fresh/upgrade table definitions checked at existing head 0028. |
| Redis dispatch recovery | PASS, synthetic | `test_postgres_redis_comment_job_is_recoverable_and_consumed_once`; committed job survives failed dispatch and is consumed once after recovery |
| Browser -> worker -> PostgreSQL -> reload | PASS, synthetic collector | 1 Playwright test passed in 4.6s; separate SQL check confirms 1 post and 2 encrypted comment versions, with correct observation/evidence version |
| Live post-only collector | PARTIAL | Current runner, 1 post, reactions/comments/share available, 2 HTTP requests, 3.23s; no comment bodies requested. Direct collector only, not UI/queue acceptance. |
| Live individual comments/replies | NOT_RUN | No current live processing decision; signed-out embedded comments are not complete pagination/replies |
| External AI / Facebook publishing | NOT_RUN | 0 provider requests, no publication |

No SQLite or inline jobs were used for the PostgreSQL/Redis/browser acceptance. The collector for pipeline tests is synthetic and visibly labeled; it is not Facebook live data.

## Disposable browser environment and database evidence

Web `13108`, API `18011`, PostgreSQL `15559/page_budget_test`, queue Redis `16481/9`, cache Redis `16482/9`. The existing preview/database/secret store were not used for these writes. No Beat ran against the fixture database.

- Job: `3e0381fc-3015-4595-a8eb-ea7e80767eb0`, status `succeeded`.
- Cycle: `903e3c32-8b05-4161-90c2-97bb56a8e173`.
- Source run: `a6f5bdae-65d9-4f99-8c83-33165188c742`, status `partial`.
- Report: `0f3883bf-33e9-4287-a350-f03991225cad`, analysis `deferred_privacy_review`.
- Observation: `45b64f14-7f18-48d2-8714-5bb91241fdb9`.
- Evidence version: `dbb01fe6-5138-4b57-9dd7-3b8ce8f5a2f1`.
- 1 post saved; 2 comment versions with ciphertext and `privacy_hold`; likes `[2, NULL]`, reactions 9 on each synthetic row.
- Source-reported count 200 versus returned count 2 remained distinct. Reload verified both rows.

Sanitized test result and screenshot were kept in the private disposable test directory, not Git. Test credentials and traces containing them are never documentation or release artifacts. Fixture data is removed during cleanup; IDs document the test run, not permanent application records.

## Reproduction

Configure dedicated PostgreSQL/Redis URLs before importing settings, with `INLINE_JOBS=0`, `AUTO_CREATE_SCHEMA=0`, and real provider keys empty. Use `POSTGRES_TEST_URL`, `POSTGRES_FRESH_TEST_URL`, `REDIS_QUEUE_TEST_URL`, `REDIS_CACHE_TEST_URL`; API runtime variables are `DATABASE_URL`, `REDIS_URL`, `REDIS_CACHE_URL`.

```sh
python -m pytest -q tests/test_postgres_public_facebook_comments.py
python -m pytest -q tests/test_postgres_comment_quarantine.py tests/test_postgres_comment_checkpoints.py
cd services/research/facebook_cli_runner
go test ./...
go build -o /absolute/test/output/facebook-cli-runner .
```

Browser test is `tests/e2e/public-page-comments.real.spec.ts`, with external server mode and an ephemeral credential file supplied through `E2E_PUBLIC_COMMENT_CREDENTIAL_FILE`. Its account/workspace/collector must belong to the test. Build for the test API origin; do not reuse that build as the user release.

## Live scope

User-saved Page tested: `https://www.facebook.com/AlorsetarPromosiSkMagic59`.
Engine: `facebook-cli@v0.3.0+8e251abf0bc6fd28acca9b9fa1cafbd07ccae39`.
Tier 0, no login/cookies; `history_complete=false`, `stop_reason=tier0_feed_exhausted`, comments_requested=false. No live commenter content was captured in this smoke.

Per-comment interaction means reactions/likes received by the comment. It does not mean a person's complete activity or a list of people who liked/shared. Aliases are scoped pseudonyms, not proof of anonymity. No claim of complete Page history, every reply, absolute redaction or legal certification is made.

## Rollout verification

PASS: frontend release `codex-page-workspaces-research-9197847d7915-20260930T214102Z`, API readiness, comment-processing/comment-list OpenAPI routes, real runtime origin 8001 with mocks off, /login, /register and local font. A fresh browser context rendered the login form with no script errors. The exact-empty-form selector initially failed because the existing control includes its disabled explanation in the accessible name; corrected check passed without a product change.

PASS: API/worker/ingestion/Beat labels restarted once, two worker names/queue routes confirmed after startup (`auth-preview-agent`: agent/default; `auth-preview-ingestion`: ingestion). Initial immediate registration check was premature; bounded follow-up passed. Existing Page verified state and persistent key configuration are preserved; owned schedule off; busy jobs 0 at verification. No migration or user password change.

Runner binary SHA-256: `c23d6c87abced068693029b7e2f4b4238eafbcc526da16e000981f7efd0dc007`. Prior runner backup and frontend release retained. No source processing assessment was fabricated for the live Page; live comment content remains NOT_RUN.

PASS cleanup: only disposable UI/API/worker processes, fixture tenant and credential files were removed; PostgreSQL 15559 and Redis 16481/16482 stopped. User preview 13104/API8001/PG15432/Redis16379/16380 remain running. Sanitized evidence above documents the fixture run after cleanup.
