# Jobber Auto-Apply — Research & Design Plan

Status: **PLAN** (no code yet). Build begins after the open decisions below are confirmed and the
user provides their application info (Phase 0).

---

## 1. Reality check (why this is designed the way it is)

Two things from research drive every decision here:

1. **Mass, identical auto-apply backfires.** J.T. O'Donnell's piece (one of the two links) is a
   caution, not a how-to: cold applications convert ~**1/500**, referrals ~**1/14**; the average
   posting gets ~**240** applicants; and recruiters increasingly **flag obvious mass-applicants
   "do-not-hire" company-wide.** Identical AI output (same four prompts → same phrasing) gets
   ignored. → **We win on targeting + per-job tailoring + quality, not volume.** Jobber already
   ranks jobs by fit, so we auto-apply to the *top* of a scored pool, not everything.

2. **There is no clean "apply API."** Greenhouse/Lever/Ashby expose **read** APIs (we already use
   them) but applying is a **web form** that varies per company, with resume upload, EEO section,
   and custom screening questions. The industry-standard approach is **browser automation +
   per-form reasoning + human review before submit** (Simplify, LoopCV, Open Applier, etc. all do
   this). So: Playwright drives a real browser; an LLM handles the variable parts; a human gates
   the early runs.

**Guardrails baked in (non-negotiable):**
- **No CAPTCHA / bot-detection bypass.** A job that gates on CAPTCHA or aggressive anti-bot → **hand
  off to the user** (queued as "manual"), never solved.
- **No account creation / password entry.** Target **guest-apply** forms. Login-walled ATS (some
  Workday tenants) → hand off / manual.
- **Demographics are honest and optional.** Race, disability, veteran status, gender are voluntary
  EEO self-ID. We use **only the user's explicit choice**, defaulting to **"Decline to
  self-identify"** — never fabricated to game anything.
- **Every submit is irreversible.** Default mode is **Review-before-submit**; unattended runs are
  unlocked per validated form-type only after the user approves. Throttled + rate-limited.
- **Per-job tailoring** so applications are not identical (directly answers the article's failure mode).

---

## 2. Where it plugs into Jobber

```
Jobber scored pool ──select──▶ Auto-Apply Queue ──run──▶ Apply Engine (browser + agent)
   (existing)                    (new: status         │        │
   apply_url per job              AUTO_QUEUED)         │        └─▶ per job: open apply_url,
                                                       │            fill, tailor, (review), submit
                                                       ▼
                          Tracking: status APPLYING→APPLIED (real submit only)
                          + job_events log + Application Kit answers cached
                                                       ▼
                          Email tracker (already built) confirms receipt / catches replies
```

- **Source of truth = Jobber's board.** The queue is built from the user's scored pool (e.g. top-N
  of the current Recommended view, or jobs the user tags "Queue for auto-apply"). We reuse
  `apply_url`, `title`, `company_name`, `description_text`, and the match `score`.
- **The counter moves only on a *confirmed submit*** — status flips `AUTO_QUEUED → APPLYING →
  APPLIED` when the engine verifies the confirmation page/redirect. The existing streak/applied
  counter and Results page then reflect real applications automatically.
- **Email tracker (already built)** closes the loop: it matches confirmation/rejection/interview
  emails back to these jobs (multi-signal), so "successful applications" and outcomes flow into the
  career report with zero extra work.

---

## 3. Agent roles — decided (you asked me to decide "what agents and how")

The **run loop is deterministic Python** (queue, throttle, retry, tracking, screenshots) — no LLM
needed to babysit the batch. LLMs are used **only for the variable per-form reasoning**, in a
**cost-tiered** way (because Claude burns tokens):

| Step | Who | Why |
|---|---|---|
| **Run orchestration / batch loop** | Python engine | Deterministic, reliable, resumable — no tokens. |
| **Field mapping** (name/email/phone/location/links/resume upload) | Deterministic rules + **local Ollama (qwen3:14b)** for fuzzy label→field matching | 90% of a form is standard fields; cheap/offline. |
| **Custom question answering** (essays, "why us", screening Qs) grounded in résumé + job | **Grok** (default) | Capable, far cheaper than Claude for the per-app volume. |
| **Escalation / hard forms / low-confidence answers** | **Claude** (sparingly) | Best quality, used only when Grok is unsure — keeps token cost bounded. |
| **Routing / "which agent, is this form safe, did it submit?" decisions** | **Hermes** (optional top layer) | It's already built to route Claude/Grok/Codex as employees; good fit as the escalation manager. |
| **Visual verification** (right form? submit succeeded?) | DOM accessibility tree (deterministic) + Grok vision only if the DOM is ambiguous | Cheap first, vision as fallback. |

Access path: reuse the **Omnigent/HermesLab harness** you already have for talking to logged-in
Grok/Claude/Codex CLIs, or direct API — the engine calls a single `answer(question, context)`
seam so the backing agent is swappable per the table above.

---

## 4. Application Kit (the data we gather at build — Phase 0)

A structured, local, gitignored store (`backend/data/apply_kit.local.json`, treated like secrets)
that every application fills from. **This is what I'll ask you for at build.** Fields:

- **Identity/contact:** full name, email, phone, city/state/country, mailing address (if asked),
  LinkedIn URL, GitHub URL, portfolio/website.
- **Résumé:** the file to upload (path), plus a parsed text copy for question-answering. Optionally
  per-role résumé variants.
- **Work authorization:** authorized to work in US? require sponsorship? (yes/no) — common gating Qs.
- **Logistics:** willing to relocate? remote/hybrid/onsite preference, earliest start date, desired
  salary (or "negotiable"), notice period.
- **Voluntary EEO self-ID (optional, honest, default = decline):** gender, race/ethnicity, veteran
  status, disability status. Stored as the user's explicit choice or "Decline to self-identify".
- **Common screeners:** years of experience, education level, "how did you hear about us",
  references available (y/n), background-check consent posture.
- **Cover-letter policy:** none / generated-per-job (Grok, grounded + tailored) / a base template.
- **Per-question overrides / library:** a growing map of `question-pattern → your preferred answer`,
  so the system learns your real answers over time and reuses them (consistency + speed).
- **Edge-case answers:** free-form notes for unusual application-specific questions you want handled
  a certain way.

Secrets rule: résumé + PII live only in the gitignored local file, never committed, never logged in full.

---

## 5. Apply Engine — per-job flow

```
open apply_url in Playwright (headful Chromium, one context per job)
  ├─ detect: is this a supported ATS form (Greenhouse/Lever/Ashby/USAJOBS/generic JSON-LD apply)?
  │     └─ if CAPTCHA / login-required / unknown-blocked → mark MANUAL, screenshot, skip
  ├─ snapshot the form (accessibility tree, not pixels) → list of fields + labels + question text
  ├─ fill standard fields from the Kit (rules + local model for fuzzy labels)
  ├─ upload résumé (multipart file input)
  ├─ answer custom questions:
  │     Grok(question, {résumé, job, kit, per-question library}) → answer
  │       └─ low confidence / essay / unusual → escalate to Claude (or Hermes routes it)
  │     tailor per job (vary phrasing, pull the job's own keywords) — anti-"identical output"
  ├─ EEO section → user's explicit self-ID or "decline"
  ├─ REVIEW GATE (Phase B/C): render a filled-form summary + screenshot; user approves / edits / skips
  ├─ submit
  └─ verify success (confirmation page / redirect / thank-you text) → status APPLYING→APPLIED,
        log job_event, cache the answers; on failure → RETRY once, else mark FAILED with reason + shot
```

Modular seams: `Connector`-style **FormAdapter** per ATS (GreenhouseAdapter, LeverAdapter,
AshbyAdapter, GenericAdapter) so adding a new ATS = one file, mirroring how job connectors work.

---

## 6. Run Engine — scalable & modular (start 50)

- **RunConfig:** `{ count: 50, source: "recommended top-N" | "tagged", min_score, mode: dry|review|
  auto, throttle_seconds, ats_allowlist, stop_on_error }`.
- **Resumable queue** (a `apply_runs` + `apply_attempts` table): each job is one attempt with state
  `QUEUED→RUNNING→APPLIED|MANUAL|FAILED|SKIPPED`, a reason, and a screenshot path. Re-running resumes
  where it left off; never double-applies (idempotent on job id).
- **Throttling & politeness:** human-ish pacing, randomized delays, per-domain rate caps, a hard
  daily cap. Stops on repeated failures (circuit breaker).
- **Scale path:** the same engine runs 50 or 500 by changing `count`; concurrency is bounded
  (1–2 browser contexts at first). We validate at 50 with review, then raise the cap + unlock
  unattended per form-type that has proven reliable.
- **Counter integrity:** increments only on verified submit (not queue, not attempt) — matches your
  "counter moves on actual applications sent."

---

## 7. Phased build plan

- **Phase 0 — Kit & wiring. ✅ SHIPPED (commit e990be0).** Application Kit (`app/apply_kit.py`,
  local gitignored `data/apply_kit.local.json`, EEO defaults to decline) with GET/PUT `/apply/kit` +
  readiness check. `AUTO_QUEUED` status (hidden from feed) + a ⚡ queue button on cards + `/apply/queue`
  + `/apply/status`. New **Auto-Apply nav view**: Kit editor form + readiness banner + queue list +
  nav badge. No browser/submitting yet. → **User fills the Kit in the app before Phase A.**
- **Phase A — Dry-run harness.** Playwright opens each queued job's `apply_url`, snapshots the form,
  maps fields, generates answers, and **produces a filled-form preview + screenshot WITHOUT
  submitting.** Proves reading/mapping/answering end-to-end, safely. Verify on ~10 jobs.
- **Phase B — Greenhouse adapter + review-submit.** One ATS first (Greenhouse = cleanest). Fill →
  review gate → real submit → verify success → status/counter update. Run the first **50** here,
  each reviewed, until it's clean.
- **Phase C — Lever + Ashby adapters + custom-Q agent (Grok/Claude tiering).** Broaden coverage;
  harden custom-question answering + EEO handling; keep review mode.
- **Phase D — Unattended + scale.** Unlock unattended submission per validated adapter; raise the
  cap past 50; circuit breakers + daily caps. Email-confirm loop (already built) verifies receipts.
- **Phase E — Learning loop.** Per-question answer library grows; outcomes (offer/reject via email)
  feed the existing career report so targeting improves over time.

Each phase ships behind a flag, is tested on a small batch, and only then scales — same discipline
as the rest of Jobber.

---

## 8. Decisions — LOCKED (confirmed 2026-08-20)

1. **Submission autonomy:** ✅ **dry-run → review-each → unattended-per-adapter.** Never unattended
   until an ATS adapter is proven; every early submit is human-approved.
2. **Cover letters / long answers:** ✅ **generate tailored per job (Grok), grounded in résumé + that
   job, varied each time**; escalate to Claude only on low confidence. (Directly counters the
   "identical AI output" failure mode.)
3. **Agent tiering:** ✅ **local (Ollama) + Grok default, Claude only on escalation, Hermes as router.**
4. **Source scope:** ✅ **guest-apply ATS only — Greenhouse / Lever / Ashby / USAJOBS.** Workday /
   login-walled / CAPTCHA jobs are handed off to the user as "manual" (never auto-account-created or
   CAPTCHA-solved).
5. **Risk posture:** ✅ accepted — stay **targeted (top-scored only) + tailored**, throttled, with
   review gates; automated ATS submits may bend some ToS, mitigated by low volume + human approval
   early.

→ **Next step: Phase 0.** When you say "build," I'll ask you for the Application Kit (§4) and stand up
the queue.
