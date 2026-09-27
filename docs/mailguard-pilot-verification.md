# MailGuard pilot — verification report

Verification date: 2026-09-27 (Asia/Ho_Chi_Minh)

## Build under test

- Feature branch: `codex/mailguard-pilot`.
- Base SHA: `79e23ce759f4cd32d64d6f61e3961cf9c106ae51` (`origin/codex/project-database-hardening`).
- Tested implementation commit: `5434dc5` (`feat: complete MailGuard pilot workflows`).
- Implementation and report commits are pushed to GitHub feature branch `codex/mailguard-pilot`.
- PostgreSQL: 18.3, disposable database with `pgvector` extension.
- Redis: 8.6.3, separate queue and cache instances.
- Python: 3.14.5 virtualenv (project minimum is Python 3.11); frontend built with lockfile dependencies.
- Data fixtures are test-only. No MailGuard end-customer PII was used.

## Acceptance matrix

| Requirement | Status | Evidence / limit |
|---|---|---|
| MailGuard brand facts and constraints read from MGAI document | PASS (reviewed) | Brand profile remains user-confirmed; unknown website/logo/official claims are not invented. |
| Planning returns brief and three concepts, persisted in job | PASS (unit/API code tests) | Campaign is not created until user chooses/accepts; live DeepSeek request NOT_RUN. |
| Current post review is stored by tenant/version/hash/rule | PASS | Review/approval path covered by PostgreSQL application smoke and unit/API tests. |
| Deterministic and semantic review | PASS (unit/fake adapter) | Hard rules inspect caption and CTA; configured DeepSeek can add semantic warnings with quoted-draft evidence. A fake adapter verifies the contract without a provider call. Live semantic review: NOT_RUN. |
| Approval/publish checks current review and version | PASS (code/API tests) | Edit changes version and invalidates old review/approval eligibility. No public publication sent. |
| Durable scheduled Meta publication, cancel, missed state | PASS (PostgreSQL API smoke + code review) | Schedule creation/list/cancel tested; actual clock-driven dispatch and Page publish NOT_RUN. |
| Page metric schedule default-off / six-hour interval | PASS (PostgreSQL API smoke) | Owner enable/disable persisted; Meta live read/sync NOT_RUN. |
| MailGuard event receiver and conversion cohort | PASS (unit + PostgreSQL API smoke) | Signup and first-analysis events, dedup, stable identity keying and analytics tested against opaque fixtures. |
| MailGuard conversion live | NOT_RUN | No MailGuard website exists. Integration status is `INTEGRATION_READY`; no real event count is claimed. |
| PostgreSQL fresh migration to `0018` and upgrade from `0017` | PASS | PostgreSQL 18.3/pgvector. Downgrade to `0017` then upgrade to head also passed. |
| ORM/migration parity | PASS | `alembic check`: no new upgrade operations detected. Tenant composite FKs checked in PostgreSQL. |
| PostgreSQL job fencing, contention and queue dispatch recovery | PASS (integration tests) | PostgreSQL integration file: 5 tests passed, including stale worker fencing, competing claims and durable queued job after simulated dispatch failure. |
| Queue/cache Redis instances are separate with TTL behavior | PASS (integration test) | Dedicated queue and cache ports; this did not simulate full Redis eviction or a process crash under live traffic. |
| Candidate real-mode browser/API | PARTIAL PASS | Login HTTP 200; owner workspace loaded, API `/readyz` healthy, analytics displays `INTEGRATION_READY · live NOT_RUN`; workspace persisted after browser reload. This is not an upload → generation → review → publish acceptance. |
| Full upload → Redis/Celery worker → PostgreSQL browser flow | NOT_RUN | Existing product tests cover upload/RAG on PostgreSQL. MailGuard document upload/profile confirmation and the AI workflow were not performed in browser. |
| DeepSeek live planning/generation/review | BLOCKED / NOT_RUN | `DEEPSEEK_API_KEY` and model configuration absent in this test process; no provider request was sent. |
| Meta Page read and public post | BLOCKED / NOT_RUN | Page token/app secret not configured. No public post was created; no user-selected post was available for confirmation. |
| Frontend lint/typecheck/tests/build | PASS | Lint PASS; TypeScript typecheck PASS; 47 frontend tests PASS; production build PASS. |
| Python syntax and lint | PARTIAL | AST parse passed for 56 Python files. `ruff` was not installed; lint NOT_RUN. |
| Browser mobile/a11y review | NOT_RUN | Not represented by unit tests or production build. |
| Backup/restore of this exact pilot database and storage | NOT_RUN | Existing repository backup evidence applies to earlier schema/revisions; a new candidate-specific restore drill remains outstanding. |
| Feature branch push and remote SHA | PASS | Push completed and `git ls-remote --heads origin codex/mailguard-pilot` confirmed the branch ref after each report update. |

## Commands run

```sh
pytest -p no:cacheprovider -q tests/test_campaign_workflows.py tests/test_mailguard_pilot.py
pytest -p no:cacheprovider -q tests/test_postgres_database_integration.py
pytest -p no:cacheprovider -q tests/test_postgres_application_modules.py
node scripts/gen-api.mjs --from=/private/tmp/mailguard-pilot-openapi.json
npm run lint
npm run typecheck -- --incremental false
npm run test
NEXT_TELEMETRY_DISABLED=1 npm --workspace @agentic/web run build
```

Observed results: Python unit/API **19 passed**; PostgreSQL integration **5 passed**; PostgreSQL application flow **1 passed**; frontend tests **47 passed**; lint, typecheck, generated API types and production build passed. The migration was separately exercised as described above. Python lint, live providers, full user-facing workflow, scheduler clock tick and restore drill are not included in those pass counts.

## User-facing checks still open

1. User must upload an authorized MailGuard source document, review and confirm the Brand Profile; the planner stays correctly disabled until then.
2. With DeepSeek server secret/model available, run a small live plan/generation cycle and record actual model, usage and latency. Do not invent provider evidence.
3. Keep Meta public posting NOT_RUN unless the Owner explicitly chooses and confirms a specific post to send.

Tracking success remains specifically MailGuard `signup_completed` and `first_analysis_completed`; marketing-platform account login or registration is not counted as a MailGuard conversion.
