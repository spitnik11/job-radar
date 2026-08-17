# Job Radar — roadmap & deferred decisions

Built against a detailed 71-section design spec. Phase 0 deliberately builds the thin vertical
slice that gets real, scored jobs on screen, and keeps the four architectural seams so the rest
grows without a rewrite. This file records *what was deferred and why* so nothing is lost.

## The four seams (kept — the spec's real value)

1. `JobConnector` (`app/interfaces.py`) — a new source is one new file in `connectors/`.
2. `JobRepository` — swapping SQLite → Postgres later never touches business logic.
3. `MatchEngine` — RuleBased → Hybrid/LLM is a drop-in.
4. `/api/v1/*` — the stable boundary for any future frontend (web or Electron).

## Deferred (not dropped), with reason

| Deferred | Why it can wait | Comes back at |
|---|---|---|
| Electron + PyInstaller + Windows installer | Spec §70 puts the shell last; a localhost web UI proves the core with zero packaging overhead | V1.2 |
| 4-package monorepo (apps/, packages/) | YAGNI — one `backend/` dir; the API is already the seam a second frontend would consume | when a 2nd frontend is real |
| Scam / trust subsystem, 3-layer dedup, freshness state machine | Every Phase-0 source is a direct-employer ATS (trust = 100 by construction) — nothing untrusted to defend against yet | first scraped/aggregator source |
| SQLite FTS5 | A few thousand jobs fit in memory; `LIKE` is enough | when volume demands it |
| Embeddings / semantic rerank | Deterministic scoring must work with no AI (core principle) | V1.1, as enhancement |
| Alembic | No data worth migrating yet; `schema_version` is stamped so the baseline is clean | first real schema change |
| ~~USAJOBS~~ | **Done (Phase 1)** — federal connector, query-driven, env/secrets-gated free key | shipped |
| SmartRecruiters | Company tokens hard to discover (200-with-0 for wrong ids) and the list API has no descriptions (N+1 detail fetch); low ROI vs USAJOBS | when a needed employer uses it |
| Precise geocoding | Static Tampa-Bay city table covers the commute market | V1.1 (Nominatim) |
| Resume parsing | Spec §5-7 already extracts the taxonomy → `profile.yaml` | V1.1 (re-import) |

## Shipped since Phase 0

- **Phase 1 (coverage):** USAJOBS federal connector (free-key-gated) + registry expansion (ConnectWise/Tampa).
- **Phase 2 (application tracking):** notes, auto-logged status events, pipeline Applied tab, Stage selector.

## V1.1 (after the core is proven in daily use)

Local embeddings + semantic rerank · GitHub repo importer · resume re-import · scam/trust engine
(arrives with the first untrusted source) · FTS5 · precise geocoding · background auto-sync (4h) ·
Alembic baseline · salary filters · daily digest.

## V1.2+

Electron shell + Windows installer (double-click app) · Workday / BambooHR / iCIMS connectors ·
company discovery service · repost / ghost-job detection · JobPosting JSON-LD parser for arbitrary
career sites.

## V2 / V3

Application assistant (role-tailored resume hints, cover-letter draft, interview prep — user still
clicks the final Apply). Then optionally a hosted version: Postgres + pgvector, workers, web UI,
public JobPosting pages + Google indexing.
