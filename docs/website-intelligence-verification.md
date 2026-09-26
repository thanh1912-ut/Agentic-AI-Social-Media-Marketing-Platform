# Website intelligence verification

Updated: 2026-09-26 22:21 (Asia/Ho_Chi_Minh)

## Build under verification

- Branch: `codex/website-catalog-intelligence`
- Base commit: `31935df990027d40fd83b7c55e2f92fee1abd8a0`
- Feature commit: `a8b7afb` (`feat: add structured website catalog intelligence`)
- Verified GitHub branch SHA after push: `200dca18693f16d7003d722e28606b7e742ddd39` (matched local HEAD).
- Runtime: Python 3.11 virtualenv at `/private/tmp/website-catalog-venv`; Node/npm from the repository workspace.

## Checks

| Check | Status | Evidence |
|---|---|---|
| JSON-LD/Microdata Product, ProductGroup variants, Offer, Article, and organization extraction | PASS | Focused fixtures cover variants, currencies, provenance, and structured-data conflicts. |
| Decimal price parsing and public counter precision | PASS | Approximate `1,2k`, lower bound `100+`, ambiguity, and missing-value cases are covered. |
| DOM prices and original-price extraction | PASS | WooCommerce-style fixture verifies current/original price, VND, and review count. |
| Related product card isolation | PASS | Regression fixture proves prices remain attached to their own product URLs. Live retest of the Gamma detail page returns one Gamma item at 359000 VND rather than attaching related-card prices to it. |
| Sitemap index and HTML article extraction | PASS | Sitemap fixture fetches actual pages; article fixture retains content beyond 12,000 characters. |
| Focused Python tests | PASS | `20 passed` across `tests/test_website_entities.py` and `tests/test_market_research_sources.py`. |
| Full Python suite | NOT RUN | Collection stops because this temporary virtualenv lacks the repository dependencies `celery` and `python-docx`; the focused website tests run successfully. |
| Python lint, compilation, and whitespace checks | PASS | Ruff `E4,E7,E9,F`, `py_compile`, and `git diff --check` passed on changed Python and tracked changes. |
| Migration from base through revision 0014 | PASS (SQLite only) | `alembic upgrade head` passed using the project Python 3.11 virtualenv and a new SQLite database under `/private/tmp`. |
| Migration on PostgreSQL | NOT RUN | No isolated PostgreSQL test service is available; SQLite is not evidence for PostgreSQL-specific behavior. |
| OpenAPI and generated TypeScript schema | PASS | Generated OpenAPI and API schema include catalog settings, run, and item routes. |
| Frontend lint, typecheck, unit tests, and production build | PASS | ESLint passed, TypeScript no-emit passed, Vitest `47 passed`, and Next.js production build passed. |
| Live public page extraction | PASS (crawler only) | Three one-page requests to taphoammo.vn matched visible title and price in fetched page text: Gamma 359000 VND / 6 reviews; Cursor AI 489000 VND / 2 reviews; Office 365 250000 VND. All three have no published sold count. No raw response was saved. |
| Browser real mode → API → Redis/Celery → PostgreSQL → reload | NOT RUN | No isolated PostgreSQL/Redis services and no running real-mode app in this worktree. Direct crawler execution does not prove this integration. |
| Redis recovery, worker concurrency, and durable frontier resume | NOT RUN / INCOMPLETE | Worker still performs one bounded pass; 100-page checkpoint continuation and pause/resume are not implemented. |
| JavaScript-rendered source handling | BLOCKED | Renderer remains disabled because no isolated egress proxy/container boundary was verified. |

## Data semantics

Contact or ambiguous prices are never converted to zero. Review count is not sales count. Approximate and lower-bound public counters retain their precision. The three live pages did not expose sales numbers; `sold_count` remains NULL. These are values displayed by the source, not audited transactions. The sample prices are observations at crawl time and may change.

## Acceptance status

The structured extraction/API/frontend foundation and three live crawler checks passed. The requested end-to-end product workflow is **not fully accepted** because PostgreSQL/Redis integration, browser-triggered crawling with persisted live results, full-site batch continuation, pause/resume, source-level 12-hour refresh, and safe JavaScript rendering remain incomplete or unverified. Do not describe this as a full-site crawler yet.
