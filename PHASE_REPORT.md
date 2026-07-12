# PHASE_REPORT — Phase 3 (report generator) — FINAL PoC PHASE

Date: 2026-07-03 · Status: **COMPLETE — PoC pipeline delivered end-to-end.**
Remaining open items are operator-side (golden labels ×2, REJECTED policy).

## Deliverables status (SPEC §3)

| | Deliverable | Status |
|---|---|---|
| D1 | FINDINGS.md + SQLite cache | ✅ Phase 0 — 16,215 jobs, 7 agents |
| D2 | Census tool + reports/census_report.md (Gate 0) | ✅ Phase 1 — 97.5% Regime A |
| D3 | Assessment pipeline | ✅ Phase 2 — reproducible, budget-guarded |
| D4 | Report generator + one real assessment | ✅ Phase 3 — [reports/otto_2026-06-25.md](reports/otto_2026-06-25.md) |

## Phase 3 specifics

- `src/report.py`; `make assess AGENT=<id>` now runs pipeline → report in one
  step, entirely from cache (0 API calls when cached).
- Report contains: 2-sentence methodology, window + sample size, weighted
  dimension table, 3 anonymized failure examples, full provenance block
  (source, date ranges, pull timestamps, seed, config hash, judge + rubric
  version), private footer.
- Determinism: filename date = window end (from data, not wall clock);
  re-run verified byte-identical (sha256 match).
- PDF render: pandoc not installed on this machine — optional per SPEC,
  skipped; `make assess` will emit a PDF automatically wherever pandoc exists.

## Acceptance (SPEC §9, Phase 3)

| Check | Result |
|---|---|
| One-command real assessment from cache, no manual steps | ✅ `make assess AGENT=otto` |

## Cumulative spend

≈ **$0.32 of $5.00** (judge calls; everything cached — re-runs free).

## Open operator items (close-out list)

1. Classifier golden labels — golden/classifier_candidates.csv
   (`proposed_label` prefilled, 9 borderline rows flagged) → `make test-census`.
2. Judge golden scores — golden/judge_candidates.csv (`proposed_score`
   prefilled) → `make test-pipeline` (Spearman ≥ 0.7 gate; rubric iteration if
   it fails).
3. REJECTED policy: v0 counts provider rejections against completion (Otto:
   25%). Evidence cuts both ways — sampled rejections include obvious probe
   spam (e.g. a "trinity-cross-validation-…" swap with amount 0), suggesting
   an accepted-jobs-only completion + separate acceptance-rate metric may be
   fairer. Changing this alters the headline composite; operator call.
4. Optional: raise `MAX_JOBS_PER_STATUS` (src/pull.py) and re-pull for fuller
   history; widen `window_days` if thin recent activity persists.
