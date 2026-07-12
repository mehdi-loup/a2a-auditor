# a2a-auditor

Proof of concept for an **independent reliability certifier for autonomous
agents**, built on real job data from [Virtuals ACP](https://app.virtuals.io/acp)
agents on Base. Given an agent, it produces a reproducible, private
reliability assessment from the agent's actual job history — plus a market
census as a byproduct of the same data access.

**Status: PoC complete (Phases 0–3).** See [PHASE_REPORT.md](PHASE_REPORT.md)
for current state and open items, [FINDINGS.md](FINDINGS.md) for the
data-access research, and [SPEC.md](SPEC.md) for the full specification.

## What it does

```
pull ──► cache (SQLite, raw JSON verbatim)
              │
              ├─► census: Regime A/B classification of the whole market (Gate 0)
              │
              └─► assess: seeded sample ─► V1 completion
                                           V2 evidence (on-chain receipt check)
                                           V3 conformance (LLM judge, identity-blind)
                                           V4 latency (vs job-type medians)
                                           ─► weighted composite ─► private report
```

Headline results from the initial run (2026-07-03):

- 16,215 real jobs cached across 7 ACP agents; **97.5% are Regime A**
  (≤ $50, ≤ 10 min, instantly verifiable) — confirming the market thesis.
- A live assessment surfaced a **98.7% (registry, lifetime) vs 25%
  (independent, last 60 days)** completion gap for a top agent.
- Every sampled settlement transaction verified against Base mainnet.

## Principles

- **Determinism** — seeded sampling; every LLM/RPC response cached in SQLite;
  `make assess` twice ⇒ byte-identical report. Any score is re-derivable from
  the cache alone.
- **Provenance** — every report states data source, date ranges, pull
  timestamps, seed, config hash, judge model + rubric version.
- **No fabricated data** — if a data route fails, it's documented in
  FINDINGS.md; nothing is mocked.
- **Read-only** — no keys, no wallets, no transactions. RPC reads only.
- **Budget-guarded** — judge runs abort before exceeding the configured cap.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
make setup
cp .env.example .env   # add ANTHROPIC_API_KEY (only needed for assessments)
```

## Usage

```sh
make pull AGENT="Otto AI"    # fetch & cache an agent's job history
make census                  # market census → reports/census_report.md
make assess AGENT=otto       # full pipeline → reports/<agent>_<date>.md
make test                    # phase acceptance checks
```

## Layout

```
src/          pipeline modules (no framework)
data/         SQLite cache + raw pulls        (gitignored)
reports/      census + assessments            (gitignored — private artifacts)
golden/       hand-labeled calibration sets   (committed)
config.yaml   seed, weights, thresholds, budget cap
```

---
Assessment reports are private outreach artifacts — not for distribution.
