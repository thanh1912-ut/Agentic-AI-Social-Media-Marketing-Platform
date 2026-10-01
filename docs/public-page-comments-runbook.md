# Public Page comments — runbook

## Scope and operation

Competitor and market/news Pages use `competitor_facebook_page` + `public_web`, with the pinned signed-out facebook-cli runner. Owned Page Meta collection, website crawling, AI providers and publishing retain their existing paths.

The runner reads comments embedded in the signed-out permalink response. It does not call authenticated comment pagination, log in, use cookies or enumerate people who liked/shared. It returns separate post/comment metrics, raw abbreviated counts and coverage. Failed detail reads preserve valid feed posts.

1. Open Research -> Thu thập and add/select a public Fanpage source.
2. Record purpose and processing basis through the existing source policy.
3. Owner records a source-scoped local-processing assessment under Bài viết & lịch sử -> Bình luận công khai. This is recorded once for the configured period (UI 7 days, API at most 30 days), not requested on every crawl. It is not commenter consent or a platform legal certification and does not authorize AI transmission.
4. Click Crawl ngay. Missing/expired scope leaves post collection working and does not request comment bodies.
5. Open Xem bình luận và tương tác under a post. Owner sees scoped aliases, redacted text, likes, reactions, reply count and timestamps when actually returned. NULL, approximate counts and unknown authors are labeled.
6. Revoke scope to remove encrypted candidate bodies. Candidates expire after at most 24 hours; API blocks expired access immediately, and the scheduler purges expired ciphertext in bounded batches.

All these candidates remain `privacy_hold`; they are not sent to Gemini/DeepSeek or used as approved Content Agent knowledge. Opening Research does not start a crawl. Existing schedules remain as configured by the user. A failed read retains older post data with its original observation time.

## Persistent runtime configuration

```dotenv
FACEBOOK_CLI_RUNNER_PATH=/absolute/runtime/path/facebook-cli-runner
META_TOKEN_ENCRYPTION_KEY=<existing persistent key; do not regenerate>
DATABASE_URL=<application PostgreSQL connection>
REDIS_URL=<isolated queue instance/database>
REDIS_CACHE_URL=<cache instance/database>
AUTO_CREATE_SCHEMA=0
INLINE_JOBS=0
NEXT_PUBLIC_USE_MOCKS=0
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

The subprocess does not inherit database/provider/Page credentials or proxy/session settings. Do not place secrets in the checkout, frontend, logs or plist.

Upstream pin: facebook-cli v0.3.0, commit `8e251abf0bc6fd28acca9b9fa1cafbd07ccae39`, with existing go.mod/go.sum. Build from `services/research/facebook_cli_runner` during deployment, not each job. Runtime adapter is public-comments-v1 / Facebook post adapter v2.

Limits: 20 actual HTTP requests, 2-second pacing, 5-minute source budget; up to 100 embedded comments per post and 500 per batch. There is no Tier 0 continuation to read all replies. Stored comment review pages default to 25 and max 100. Comments are truncated at 20,000 characters with an explicit flag.

The public-comment implementation9197847 used existing0028 tables. The erasure update requires additive `0029_comment_suppression`; use [the deletion runbook](comment-deletion-runbook.md) before restore or rollback. Page activation, active source/current policy, Owner membership, processing decision and job fencing are rechecked at persistence.

## Checks

Use the checkout's documented Python/Node/Go dependency runtime, with provider keys empty for automated tests:

```sh
python scripts/export_openapi.py --check
npm --workspace @agentic/web run gen:api -- --from ../../packages/contracts/openapi.json
npm --workspace @agentic/web run lint
npm --workspace @agentic/web run typecheck
npm --workspace @agentic/web run test
NEXT_PUBLIC_USE_MOCKS=0 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm --workspace @agentic/web run build
```

PostgreSQL/Redis acceptance and the browser fixture setup are described in [verification](public-page-comments-verification.md). Use dedicated databases/ports. Do not stop services at 5432/6379 or purge shared queues to test failures.

## Rollout, stop and rollback

User preview: frontend `13104`, API `8001`, PostgreSQL `15432`, queue `16379/4`, cache `16380/4`. Runtime files live outside the checkout; existing Page/Gemini keys are preserved.

1. Check that this preview has no queued/running jobs. Preserve current schedule intent and the disabled owned-Page schedule.
2. Build the runner to a temporary path, verify it, back up the configured binary, atomically replace only that binary.
3. Drain/restart only the identified LaunchAgents: auth-preview-beat/api/worker/ingestion. Wait for labels to unload; bootstrap with bounded retries. Do not run the whole environment installer.
4. Check /readyz, the two distinct worker nodes and their queues (`default,agent` and `ingestion`).
5. Build frontend with API 8001 and mocks off. Activate an immutable release using `apps/web/scripts/creative-studio-preview.py activate`; this changes only `com.agentic-marketing.auth-preview-web` and retains its previous release.
6. Verify /login, static assets, runtime API origin and the new OpenAPI routes. No provider call or Facebook publication is required for health checks.

Stop only identified preview labels with launchctl bootout; keep PostgreSQL/Redis/storage unless deliberately stopping this whole known environment. Reload a specific label using its existing plist and verify readiness. Do not regenerate encryption/JWT keys or reset accounts.

Frontend rollback: `creative-studio-preview.py rollback` restores the prior web release. For collector rollback, restore the backed-up binary and previous application version together after draining workers. Preserve Page/tenant gates and database history. Missing new runner capability must not be hidden by a logged-in fallback. Revoking a source's processing scope immediately disables new comment persistence and deletes its candidate ciphertext.

## Troubleshooting

- `engine_unavailable`: verify executable path, build and permissions; do not install/download during a job.
- `processing_required`: Owner needs a current source policy/decision; do not fabricate a legal assessment.
- `login_required`, `challenge`, `access_denied`: record the real access result; no cookie/login workaround.
- 0 returned versus positive reported count: embedded comments were not supplied; it is partial coverage.
- Like absent but reactions present: do not copy reactions into likes.
- Hidden/expired comment rows: candidates have at most 24-hour access, or the policy/decision changed.
- Cursor conflict: a new observation was collected; reload the post review.
- Provider unavailable: post/comment persistence is independent; held comments never go to AI.

Operational pseudonymization/redaction is not a guarantee of complete anonymity or a legal compliance certification. Retention/processing obligations require the operator's verified source-specific assessment.

## Active erasure release

Code `c221b01cd38b129f29650fe5edd8608cf8dde0d6`, runtime/frontend build HEAD `b96e785ffe5d35e149b8597d62c4cb41c9cc640c`, release `codex-page-workspaces-research-b96e785ffe5d-20261001T074846Z`. Preview schema0029, real13104/API8001; previous frontend release retained. Maintenance backup `page-comment-suppression-maintenance-20261001T074755Z` outsideGit/private permissions. API and two worker nodes are ready. No live comments decision or AI call was created.

See [comment-deletion-runbook.md](comment-deletion-runbook.md) before backend rollback/restore. Preserve ledger enforcement; downgrade0029 is blocked. The old binary backup below concerns the public-comment extraction release, not permission to roll back suppression guards.

## Previous public-comment release — history

Implementation `9197847d7915ec2520feca417c8d33fb30b659b1` is deployed. Runner backup: `/Users/lethanh/.local/share/agentic-marketing/auth-preview/bin/facebook-cli-runner-before-public-comments-9197847`. Frontend release `codex-page-workspaces-research-9197847d7915-20260930T214102Z`; the existing frontend rollout state retains the prior plist/release for rollback.

For the specific worker label, after draining jobs:

```sh
launchctl bootout "gui/$(id -u)/com.agentic-marketing.auth-preview-worker"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.agentic-marketing.auth-preview-worker.plist"
```

Wait until the label has fully unloaded before bootstrap and allow bounded time for worker registration. Do not change another preview's labels or secrets. The disposable verification services have been stopped; start dedicated test infrastructure again before rerunning database/browser acceptance.
