# Job Radar

Local-first personal job-intelligence tool. It pulls real postings from trusted employer ATS
APIs, normalizes them, filters out senior/out-of-area/scam listings, scores each against one
candidate profile with an **explainable** weighted match, and presents them in a minimal
split-pane UI that links straight to the real Apply page.

Not an Indeed clone — it answers four questions per posting: *is it real, is it open, am I
plausibly qualified, is it worth applying now?*

## Status — Phase 0 (thin vertical slice)

Working end-to-end today:

- **Sources:** Greenhouse, Lever, Ashby (public JSON, no auth) over a seed company registry
- **Pipeline:** fetch → normalize → enrich (skills / experience / seniority) → hard-scam guard →
  explainable score → location + seniority filter → exact-URL dedupe → SQLite (WAL)
- **Matching:** deterministic weighted score (role/skills/experience/portfolio/location/education/
  freshness/source) with a per-factor "why it matches" breakdown + a separate application-priority score
- **UI:** split-pane list + detail, filters, instant search, Save/Dismiss/Apply, keyboard nav
- **API:** versioned `/api/v1/*` (the stable seam for a future Electron or web frontend)

Deferred on purpose (see `docs/roadmap.md`): Electron packaging, the full scam/trust subsystem,
FTS5, embeddings, Alembic, USAJOBS/SmartRecruiters. The four interface seams (connector /
repository / match-engine / versioned API) are in place so none of that needs a rewrite.

## Run it (Windows, from `backend/`)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --port 8000
```

Open http://localhost:8000, click **Sync** to pull fresh jobs (first sync ~1-2 min), then browse.

Sync from the CLI instead: `.\.venv\Scripts\python -m app.ingestion.pipeline`
Run the tests: `.\.venv\Scripts\python -m pytest`

## Make it yours

- `data/profile.yaml` — skills, weights, education, home city (already seeded from the resume)
- `data/settings.yaml` — radius (45 mi), remote/hybrid/onsite, min score, target roles
- `data/companies.yaml` — the seed ATS boards; **add local Tampa Bay employers here** to grow coverage

## Layout

```
backend/app/
  connectors/   greenhouse · lever · ashby  (add a source = one file)
  matching/     skills · seniority · location · scorer
  ingestion/    pipeline · scam guard
  api/v1.py     versioned HTTP surface
  repository.py SQLite (only place business logic touches the DB)
backend/web/index.html   single-file UI
backend/data/*.yaml      profile · settings · companies
```
