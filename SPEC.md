# SPEC — Agent Reliability Assessment Pipeline PoC (Regime A scope)

Version 0.1 · Source of truth for this repo. Read fully before writing code. CLAUDE.md defines working rules.

## 1. Background & purpose

We are testing the foundations of an independent reliability certifier for autonomous agents. Agent-to-agent work splits into two regimes:

- **Regime A**: low-value, atomic, instantly/deterministically verifiable jobs (the vast majority of current volume).
- **Regime B**: consequential, non-atomic, judgment-based delegated work (nearly empty today; the eventual business).

This PoC is scoped to **Regime A** because that data exists at volume and is objectively verifiable — ideal for proving the pipeline end-to-end and calibrating the LLM judge. It does **not** test willingness-to-pay or Regime-B semantic verification.

**PoC goal:** given a real agent on Virtuals ACP, produce a reproducible, private reliability assessment from its actual job history — plus a market census (Gate 0) as a byproduct of the same data access.

## 2. Definitions

- **Regime A job**: price ≤ $50 AND deterministic/instant verification AND duration ≤ 10 min. Any of {price > $50, non-instant verification, > 10 min} ⇒ **Regime B**.
- **Assessment**: a private report scoring one agent's reliability over a sampling window.
- **Golden set**: hand-labeled jobs used to calibrate classifier and judge (operator provides labels; pipeline provides candidates).

## 3. Deliverables

- **D1** — `FINDINGS.md` (data-access spike) + cached dataset in SQLite
- **D2** — Census tool + `reports/census_report.md` (this is Gate 0)
- **D3** — Assessment pipeline (sampling → verification → scoring)
- **D4** — Report generator + one real assessment (default target: Ethy AI)

## 4. Phases

### Phase 0 — Data-access research spike (time-box: 1 day)

Questions: how to enumerate ACP agents; how to pull one agent's job history (request, deliverable, status, price, timestamps, counterparty).

Try in order, documenting each:
1. **Virtuals ACP public API** — inspect docs.virtuals.io, app.virtuals.io network calls, and the open-source `acp-cli` / virtuals-protocol GitHub repos (their internals reveal endpoints).
2. **Base on-chain** — ACP contract events (job lifecycle), decoded via verified-contract ABIs; enumerate via event logs over a bounded block range.
3. **Indexers** — community subgraphs / explorers (x402scan-style) exposing ACP job data.

Acceptance: `FINDINGS.md` covering every route tried (works / fails / why, with endpoints or contract addresses), and — if any route works — ≥ 500 jobs for at least one high-volume agent cached per §6.

Kill criterion: no programmatic route works → write `FINDINGS.md` with remaining options (manual export, partnership ask) and **STOP**. Do not mock data.

### Phase 1 — Census / regime classifier (Gate 0)

Classify all cached jobs into Regime A/B per §2. Output `reports/census_report.md`: job totals, value distribution, job-type breakdown, regime split, top agents by completed volume.

Acceptance:
- ≥ 1,000 jobs classified across ≥ 5 agents (or the maximum the data source allows — state the constraint).
- Classifier agrees with the human-labeled 50-job golden set ≥ 90%.

### Phase 2 — Assessment pipeline

**Sampling**: seeded random sample, n = min(200, 10% of the agent's jobs in the last 60 days). Seed lives in `config.yaml`; identical seed + cache ⇒ identical sample.

**Verification checks per sampled job**:
- **V1 Completion** — delivered vs failed/expired/abandoned (from status data).
- **V2 Evidence** — deliverable URI/hash present and resolvable; settlement evidence present in chain data.
- **V3 Conformance** — LLM judge scores 0–10 whether the deliverable addresses the request (rubric §7).
- **V4 Latency** — request→delivery seconds, percentile vs that agent's job-type median.

**Scoring v0** (weights in config, defaults):
composite (0–100) = completion 35% + conformance 30% + evidence 20% + latency 15%. Report per-dimension subscores alongside the composite. Weights are explicitly provisional — the rubric is the product's core IP and will be iterated.

Acceptance:
- Reproducibility: two runs on the same cache + seed ⇒ identical composite.
- Judge stability: 3 judge passes on the golden set at temperature 0 ⇒ per-item variance ≤ ±0.5.
- Calibration: judge vs human labels on the 20-job golden set, Spearman ≥ 0.7. If < 0.7, iterate the rubric prompt (log each iteration) before proceeding.

### Phase 3 — Report generator

`make assess AGENT=<id>` produces `reports/<agent>_<date>.md`: methodology (2 sentences), window + sample size, composite + dimension table, 2–3 anonymized failure examples, provenance block (source, block/date range, pull timestamp, seed, config hash), and footer: **"Private assessment — not for distribution."** Optional PDF render (pandoc or weasyprint).

Acceptance: end-to-end run from cache for the default target completes without manual steps.

## 5. Non-goals — DO NOT BUILD

Badge registry · bond/staking contracts · challenge game · ERC-8004 writes · any on-chain transaction · public website or publishing pipeline · payments/subscription billing · Regime-B semantic deep-verification · synthetic paid probe jobs (requires a wallet; out of scope).

## 6. Data schema (SQLite, `data/acp.db`)

```
agents(agent_id PK, name, endpoints_json, first_seen, jobs_total)
jobs(job_id PK, agent_id, requester_id, ts_request, ts_delivery,
     job_type, price_usd, request_uri, deliverable_uri, status,
     chain_evidence_json, raw_json)
```
Preserve `raw_json` verbatim for every record — scores must be re-derivable from cache alone.

## 7. LLM judge rubric v0

Judge: Anthropic API, model `claude-sonnet-4-6`, temperature 0. Optional local fallback: Qwen3 via Ollama at `http://localhost:11437` — if used, flag the quality tradeoff in the report.

The judge receives **request + deliverable only** — never the agent's name/identity (bias control).

System prompt core: "You are scoring whether a deliverable fulfills a job request. Score 0–10. 10 = fully addresses the request, correct format, internally consistent. 5 = partially addresses it or has format/consistency defects. 0 = empty, unrelated, or contradicts the request. Output JSON: {score, one_sentence_reason}."

Include 3 few-shot anchors (a 10, a 5, a 0) drawn from the golden set once labeled.

Budget guard: abort an assessment run if judge spend exceeds $10 (configurable).

## 8. Open questions for the operator

1. Confirm first target agent once Phase 1 shows whose data is accessible (default: Ethy AI).
2. Approve judge budget cap (default $10/run).
3. Provide golden-set labels when the pipeline surfaces the 50 (classifier) + 20 (judge) candidates.

## 9. Acceptance summary

| Phase | Pass condition | Verified by |
|---|---|---|
| 0 | Working data route + ≥500 jobs cached, or documented STOP | FINDINGS.md + `make test-data` |
| 1 | ≥1,000 jobs classified; ≥90% golden agreement | census_report.md + `make test-census` |
| 2 | Reproducible composite; judge Spearman ≥0.7; variance ≤±0.5 | PHASE_REPORT.md + `make test-pipeline` |
| 3 | One-command real assessment from cache | reports/ output |
