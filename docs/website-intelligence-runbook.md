# Website intelligence runbook

## Current scope

New website sources use `site_catalog`; older sources remain in `legacy` until an Owner or Editor switches them. HTTP collection keeps the current public-address/DNS pinning, redirect, robots, timeout, and response-size safeguards.

The extractor reads bounded JSON-LD, Schema.org Microdata, and common product-card/detail DOM patterns. It stores normalized product, offer, article, and organization/business snapshots with source URL and extraction provenance. DOM selectors are heuristic and will not identify every site-specific catalog. It does not execute inline scripts or interact with forms. The optional JavaScript mode is rejected until egress isolation is configured and verified.

Prices use decimal strings/Numeric values. Currency and each offer remain separate; old prices are recorded only when visibly marked. Contact, ambiguous, absent, or unparseable prices are not zero. Public review counts and sales counts are separate; approximate values preserve their precision. Article text is retained up to 100,000 normalized characters, while the existing market evidence/model context remains capped at 12,000 characters.

Discovery reads same-host sitemap hints and sitemap indexes (up to 50 sitemap documents) and follows same-host HTML links through depth 6. The in-memory frontier is capped at 5,000 candidates. Sitemap URLs are fetched as pages. The current worker makes one bounded pass and runs at most 25 pages per source, even though the settings API accepts a requested limit up to 1,000. PostgreSQL page rows record processed pages, but the full discovered frontier is not yet persisted/resumed. A completed or partial run does not mean the whole domain was scanned. Batch continuation, pause/resume, and independent per-source 12-hour refresh are still pending.

## Database and API

Migration 0014 adds tenant-scoped crawl runs and pages, website entities, immutable entity/offer snapshots, and report-to-snapshot references:

```text
research_source ── web_crawl_run ── web_crawl_page
       │                  │
       └── web_entity ── web_entity_snapshot ── web_offer_snapshot
                              │
market_evidence_version ─ market_observation
                              │
market_report ── market_report_web_snapshot
```

The API prefix is `/api/v1/workspaces/{workspace_id}/market-research`:

- `PATCH /sources/{source_id}/crawl-settings`
- `GET /sources/{source_id}/crawl-runs`
- `GET /groups/{group_id}/web-items?kind=product&limit=25`
- `GET /web-items/{item_id}`
- `GET /web-items/{item_id}/snapshots`

Price filtering requires a currency; no implicit conversion is done. Settings accept page limits 1..1000 and `http_only`; `javascript` is unavailable. The effective worker ceiling is currently 25 pages per pass.

## Local checks and migration

Use the repository's virtualenv/runtime and isolated test services. Keep secrets in backend environment or a secret store; never place them in docs or `NEXT_PUBLIC_*` values.

```sh
alembic upgrade head
pytest -q tests/test_website_entities.py tests/test_market_research_sources.py
npm --workspace apps/web run lint
npm --workspace apps/web test -- --run
```

The migration was verified on SQLite from revision 0001 through 0014. Production uses PostgreSQL; run the migration and integration checks against a dedicated PostgreSQL database before deployment. Do not point migration tests at a user's existing database.

## Operating and troubleshooting

- Add a public website source, then use **Crawl ngay** in Fanpage & thị trường.
- Read crawl-run counters and item results through the endpoints above. A source run can be `partial` because the worker performs one capped pass.
- If settings request JavaScript mode, expect `renderer_unavailable` until network egress isolation is available.
- If robots or public DNS checks fail, preserve the source error; do not bypass the checks or use browser cookies.
- If a price is absent or ambiguous, review the source evidence and provenance. Do not fill it from a neighboring card, review count, search cache, or model output.
- Stop only API/worker processes started specifically for this worktree. Do not stop services from the shared checkout or other tests.

## Outstanding release work

Implement and test durable frontier continuation in 100-page batches, pause/resume, independent 12-hour source scheduling, and report finalization across resumed runs. Then test tenant isolation, duplicate delivery, recovery, and worker concurrency against isolated PostgreSQL and Redis, and prove the real browser → API → queue → worker → database → reload path. Keep Playwright disabled unless a network boundary protects every browser request and redirect.
