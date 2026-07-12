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

## Golden-set calibration — CLOSED (2026-07-12)

Operator reviewed both sets (labeled the 9 flagged classifier rows directly,
accepted proposals on the clear-cut rest; overrode 4 of 20 judge scores).

| Gate | Requirement | Result |
|---|---|---|
| Classifier vs golden labels | ≥ 90% | **100%** (50/50) |
| Judge vs operator scores | Spearman ≥ 0.7 | **0.783** (20 items) |

All SPEC §9 acceptance criteria for Phases 0–3 are now fully closed.

## Open operator items (close-out list)

1. ~~Classifier golden labels~~ ✅ closed, see above.
2. ~~Judge golden scores~~ ✅ closed, see above.
3. ~~REJECTED policy~~ ✅ **decided (operator, 2026-07-12): keep v0** —
   provider rejections count against completion. Rationale trade-off (probe
   spam in rejections) noted above for future rubric iterations.
4. Optional: raise `MAX_JOBS_PER_STATUS` (src/pull.py) and re-pull for fuller
   history; widen `window_days` if thin recent activity persists.
