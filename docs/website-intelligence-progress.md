# Website intelligence progress

Updated: 2026-09-26 22:21 (Asia/Ho_Chi_Minh)

## Current state

The structured-catalog foundation is implemented and the extractor has been checked against three live public product pages. The full product acceptance plan is still **in progress**: the current worker makes one bounded pass (at most 25 pages), and PostgreSQL/Redis plus the browser-to-worker path were unavailable for integration testing.

## Checklist

- [x] Create isolated branch `codex/website-catalog-intelligence` from `31935df` and preserve the shared checkout.
- [x] Add bounded JSON-LD, Schema.org Microdata, and conservative DOM extraction for products, offers, articles, and organization information.
- [x] Keep prices, currencies, original prices, availability, review/sales counters, and field provenance separate; ambiguous and missing values stay missing.
- [x] Separate product-card subtrees so a card cannot absorb prices from adjacent recommended items; add a regression test.
- [x] Discover same-host sitemap and HTML links with bounded depth/frontier, and preserve long article content up to 100,000 characters.
- [x] Add migration 0014 for crawl runs/pages, entities, immutable entity/offer snapshots, and report-to-snapshot references.
- [x] Persist structured evidence in the existing research worker; add tenant-scoped settings, run and item APIs, OpenAPI/types, and catalog tabs.
- [x] Pass live checks for three public taphoammo.vn product pages, each limited to one page.
- [ ] Persist and resume the complete frontier in 100-page batches; implement pause/resume and per-source 12-hour refresh.
- [ ] Run migration/integration scenarios on isolated PostgreSQL and Redis services.
- [ ] Verify browser real mode → API → Redis/Celery → PostgreSQL → reload in a real browser.
- [ ] Enable JavaScript rendering only after network egress isolation is available and verified.
- [ ] Commit and push the feature branch; verify the remote SHA.

## Baseline

- Worktree: `/Users/lethanh/.codex/worktrees/website-catalog-intelligence/agent`.
- Branch: `codex/website-catalog-intelligence`.
- Base commit: `31935df990027d40fd83b7c55e2f92fee1abd8a0`.
- Shared checkout `/Users/lethanh/agent` was not modified.
- Schema head before this feature: `0013_metric_history_and_tenant_integrity`.
- The group crawl API already dispatched durable research jobs; this change adds catalog extraction/persistence and reads on that path.

## Work log

| Time (Asia/Ho_Chi_Minh) | State | Work and evidence |
|---|---|---|
| 2026-09-26 | DONE | Added bounded JSON-LD and Microdata Product/ProductGroup, Offer/AggregateOffer, Article, and Organization extraction, including Decimal parsing, count precision, and field provenance. |
| 2026-09-26 | DONE | Added DOM extraction for common product-card/detail markup, offer prices, original prices, availability, and public review/sales labels. A live DOM issue that mixed related-card prices was fixed; fixture test `test_related_product_cards_keep_their_own_prices` covers it. |
| 2026-09-26 | DONE | Added same-host sitemap-index and breadth-first link discovery; limits include depth 6, at most 50 sitemap files, 5,000 in-memory candidates, and the existing one-pass page ceiling. |
| 2026-09-26 | DONE | Added migration 0014, tenant-scoped catalog APIs, report snapshot references, and frontend product/article/business tabs. SQLite migration from 0001 through 0014 passed in a temporary database. |
| 2026-09-26 22:09 | DONE | Focused Python suite passed 19 tests; frontend had 47 tests, lint and typecheck passed. |
| 2026-09-26 22:15 | DONE | Fixed DOM grouping so recommended products do not donate their price to the main product. Focused Python suite passed 20 tests. |
| 2026-09-26 22:18 | DONE | Read three public product URLs with `max_pages=1` each and checked title and displayed price against fetched page text. Gamma: 359000 VND, 6 reviews; Cursor: 489000 VND, 2 reviews; Office 365: 250000 VND. The pages did not publish a sold count, so it remains NULL. No raw page was saved. |
| 2026-09-26 22:20 | DONE | Final focused Python suite (20), Ruff focused checks, Python compilation, frontend lint/typecheck/tests (47), Next.js production build, `git diff --check`, and SQLite Alembic upgrade passed. |
| 2026-09-26 | BLOCKED | PostgreSQL/Redis integration, real browser smoke test, full persistent multi-batch workflow, and isolated JavaScript renderer are not verified/implemented; this environment has no isolated PostgreSQL/Redis service or browser egress boundary. |
| 2026-09-26 | IN_PROGRESS | Review final diff, commit only this feature's paths, push `codex/website-catalog-intelligence`, and confirm remote SHA. |

## Remaining acceptance work

The database now has page rows suitable for recording progress, but the worker does not yet persist and resume the discovered frontier. The 100-page batches, pause/resume operations, independent source refresh schedule, and final report orchestration across resumed batches remain outstanding. A requested source page limit can be set up to 1,000, but the current worker's effective one-pass cap is at most 25.

The live test exercised the crawler function on three public URLs. It did not press Crawl ngay in the frontend, use Redis/Celery, write the live output to PostgreSQL, or prove results survive browser reload. The JavaScript renderer remains unavailable until browser traffic can be constrained through an isolated egress boundary.
