# Job Radar

Local-first personal job-intelligence tool. It pulls real postings from trusted employer ATS
APIs, normalizes them, filters out senior/out-of-area/scam listings, scores each against one
candidate profile with an **explainable** weighted match, and presents them in a minimal
split-pane UI that links straight to the real Apply page.

Not an Indeed clone — it answers four questions per posting: *is it real, is it open, am I
plausibly qualified, is it worth applying now?*

## Status — Phase 0 (thin vertical slice)

Working end-to-end today:

- **Sources:** Greenhouse, Lever, Ashby (public JSON, no auth) + **USAJOBS** (federal, opt-in free key) over a seed registry
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
- `data/companies.yaml` — the seed ATS boards; **add local Tampa Bay employers here** to grow coverage (ConnectWise is already in)

### Turn on federal jobs (USAJOBS) — strong fit for Tampa IT

USAJOBS covers MacDill AFB, SOCOM/CENTCOM and VA roles — heavy on entry-level IT support. It needs
a **free** key:

1. Request one (instant): https://developer.usajobs.gov/apirequest/
2. `cp backend/data/secrets.local.example.yaml backend/data/secrets.local.yaml` and paste your key +
   registered email (that file is gitignored). Or set env vars `USAJOBS_API_KEY` / `USAJOBS_EMAIL`.
3. Sync. Without a key the source is inert (no error). Search keywords live under `usajobs:` in
   `companies.yaml`; location + radius come from your profile.

### Portfolio evidence from GitHub

Click **Import from GitHub** in the right sidebar (or `POST /api/v1/profile/github/import`) to pull
your public repos' languages/topics/descriptions into your portfolio-skill evidence — the scorer's
portfolio factor then reflects real shipped work, and existing jobs are rescored on the spot. Set
`github.username` in `profile.yaml` (public repos only; a token for private repos is a later add).

### Tighter local radius (optional geocoding)

The radius uses a built-in Tampa-Bay city table by default (fully offline). To resolve *any* city
precisely, set `geocoding.enabled: true` in `settings.yaml` — it geocodes table-misses via
OpenStreetMap Nominatim (cached to `data/geocode.cache.json`, rate-limited).

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
