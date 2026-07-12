# CLAUDE.md — Agent Reliability Assessment PoC (Regime A)

PoC for an independent agent-reliability certifier: prove the assessment pipeline end-to-end on real Regime-A job data from Virtuals ACP agents, producing private reliability reports. **SPEC.md is the source of truth — read it fully before writing any code.**

## Hard guardrails

- **Scope**: build ONLY what SPEC.md §4 defines. Never build: badge registry, bond/staking contracts, challenge game, ERC-8004 writes, public website, payments/billing, Regime-B semantic verification, synthetic paid probes. If a task seems to require one of these, stop and flag.
- **Data integrity**: NEVER fabricate, simulate, or mock ACP/on-chain data to unblock a phase. If Phase 0 finds no viable access route, write FINDINGS.md and STOP.
- **Read-only chain**: no private keys, no wallets, no transactions anywhere in this repo. RPC reads only.
- **Privacy**: assessments are private outreach artifacts. Output to `./reports/` only; no publishing, no uploads, no third-party services beyond the RPC, data source, and LLM API.
- **Phase discipline**: complete a phase → run its acceptance checks → write PHASE_REPORT.md → STOP for operator review. Never start the next phase unsolicited.
- **Secrets**: via `.env` only (gitignored). Never commit or print keys.

## Environment

- Ubuntu (GCP L4 `north-hermes-l4` or local), Python 3.11+
- Deps: `web3`, `requests`, `pandas`, `pydantic`, `anthropic`, `pyyaml` (sqlite3 is stdlib). Install with `pip install --break-system-packages` if system Python.
- `BASE_RPC_URL` — Base mainnet, read-only
- `ANTHROPIC_API_KEY` — judge model `claude-sonnet-4-6`
- Optional local judge fallback: Ollama Qwen3, `http://localhost:11437` (no-think proxy). If used, flag quality tradeoff in the report.

## Layout

```
/src        pipeline code (small typed modules, no framework)
/data       sqlite cache + raw pulls        (gitignored)
/reports    census + assessments            (gitignored)
/golden     hand-labeled calibration sets   (committed)
config.yaml seed, weights, budget cap, window
SPEC.md · FINDINGS.md · PHASE_REPORT.md
```

## Commands (define in Makefile during Phase 0/1)

- `make setup` — deps + db init
- `make pull AGENT=<id>` — fetch & cache job history
- `make census` — Gate 0 report
- `make assess AGENT=<id>` — full pipeline → report
- `make test` / `make test-data` / `make test-census` / `make test-pipeline`

## Conventions

- **Determinism**: seeded sampling (seed in config.yaml); cache all raw inputs; any score must be exactly re-derivable from cache. `make assess` twice ⇒ byte-identical numbers.
- **Provenance**: every report states data source, block/date range, pull timestamp, seed, and config hash.
- **Judge calls**: temperature 0; agent identity stripped from judge inputs; respect the budget cap in config (abort past it).
- Prefer boring, inspectable code over cleverness. This pipeline's outputs must survive scrutiny — it is itself a credibility artifact.

## When blocked

Prefer a documented partial result over a silent workaround. If an external interface differs from SPEC assumptions, record it in FINDINGS.md and adapt; if the difference invalidates a phase's acceptance criteria, STOP and flag for the operator. When several data routes work, pick the one with the best provenance (on-chain > official API > indexer) and say why.
