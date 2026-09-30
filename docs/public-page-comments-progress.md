# Public Page comments — progress

Updated: 2026-10-01 04:32 Asia/Ho_Chi_Minh.
Branch: `codex/page-workspaces-research`.
Baseline: `1b29ab4c99872246fa44565a70345f9762039af3`.
Implementation SHA and rollout are recorded after the commit below.

| Work | Status | Evidence |
|---|---|---|
| Competitor and market/news Pages | DONE | Same public Page source/collector; owned Meta collector preserved |
| Signed-out permalink and embedded comment extraction | DONE | Pinned facebook-cli v0.3.0; verified Page/post identities; no authenticated pagination |
| Interaction per comment | DONE | Separate likes/reactions, reaction breakdown, reply count, original abbreviated count and precision; missing is NULL |
| Personal data handling | DONE for local review | Per-post/read aliases, unknown authors qualified, contact redaction, encrypted candidates, Owner-only review, 24-hour access expiry; no external AI transmission |
| Persistence and API | DONE | Existing 0028 tables; immutable observation/version binding, replay receipt, active policy/decision recheck, lease fencing |
| Frontend | DONE | Source-scoped configuration, paginated comments, coverage and errors; cache evicted on hide/revoke |
| Python/Go/frontend checks | DONE | 180 Python regression tests, full Go tests/build, 56 frontend tests, lint/typecheck/OpenAPI/build |
| PostgreSQL and Redis acceptance | DONE with synthetic collector | Concurrent replay, stale-worker rejection, history preserved, queue recovery and actual Celery consumption |
| Browser -> Redis/Celery -> PostgreSQL -> reload | DONE with synthetic collector | 1 post, 2 encrypted comment versions; browser result independently checked by SQL |
| Direct live public Page collection | PARTIAL | Current runner: 1 post, reactions/comments/share fields present, 2 HTTP requests, 3.23 seconds; comments not requested |
| Live individual comment collection | NOT_RUN | No live source has a current local-processing decision; no assessment was invented |
| Commit, push, preview rollout | IN_PROGRESS | Required checks now run; earlier automatic review quota blocker has cleared |

The earlier 03:44 draft was not deployed. Automatic review accepted isolated test/setup actions in this turn; the old quota exhaustion is no longer a current blocker.

The initial browser harness failed because its build pointed to API 8001 instead of the disposable API 18011. It was rebuilt for the test API. A synthetic fixture email also failed normal email validation, then a selector matched both group/source crawl controls. Those harness issues were fixed; the final browser test passed. User accounts and preview configuration were not changed for testing.

No provider call, Facebook publication, user password reset, shared-index modification or shared-queue purge was performed for this slice. Existing source schedule intent is preserved.
