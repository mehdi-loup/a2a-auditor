# FINDINGS — Phase 0 data-access spike

Date: 2026-07-03 · Operator: mln · All results below are from live requests
made during the spike; nothing is simulated.

## Verdict

**A programmatic route works.** The official Virtuals ACP REST API exposes any
agent's full job history — including deliverable content and on-chain tx
hashes — via unauthenticated read-only GETs. 3,404 real jobs for one
high-volume agent (Arbus) are cached in `data/acp.db` per SPEC §6.
Acceptance: `make test-data` passes.

## Route 1 — Virtuals ACP public API: **WORKS (chosen route)**

Endpoints were discovered by reading the official SDK source
([Virtual-Protocol/acp-python](https://github.com/Virtual-Protocol/acp-python)),
then verified live.

Base URL: `https://acpx.virtuals.io/api` (prod, Base mainnet)

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /agents/v4/search?search=<kw>&top_k=<n>` | none | Enumerate/search agents; returns `walletAddress`, job offerings with prices, `metrics` (successfulJobCount, successRate, uniqueBuyerCount) |
| `GET /jobs/completed?pagination[page]=P&pagination[pageSize]=N` | header `wallet-address: <addr>` — **no signature; any agent's address is accepted** | Full completed-job history for that wallet |
| `GET /jobs/cancelled?...` | same | Rejected + expired jobs |
| `GET /jobs/active?...` | same | In-flight jobs |
| `GET /accounts/job/<id>` | none | Client/provider account for a job |

Job objects contain everything SPEC §6 needs:

- `id`, `phase` (0 REQUEST … 4 COMPLETED, 5 REJECTED, 6 EXPIRED — enum from SDK
  `models.py`), `clientAddress`, `providerAddress`, `providerName`
- `price` + `priceTokenAddress` — predominantly USDC on Base
  (`0x833589…2913`), i.e. USD 1:1. **This resolves the token→USD concern for
  ~95% of sampled jobs.**
- `deliverable` — full response content inline (no URI resolution needed)
- `memos[]` — request content, phase transitions, timestamps, and
  **`txHash`/`signedTxHash` per memo**, giving on-chain settlement evidence
  for V2 without a separate indexing pipeline
- `createdAt` / `updatedAt` — request/delivery timestamps for V4 latency
- `meta.pagination.total` — exact per-status job counts

Caveats:

- The header-only auth is undocumented behavior; it could be restricted at any
  time. Mitigation: cache aggressively (done), and Route 2 remains as fallback.
- `pageSize=100` works; pulls are throttled at 0.5 s/page in `src/pull.py`.
- `src/pull.py` caps at 2,000 jobs per status per pull (Arbus has 3,461
  completed total). Raise `MAX_JOBS_PER_STATUS` when full history is needed.

## Route 2 — Base on-chain events: **VIABLE (verification channel)**

- The SDK-configured "contract addresses" (`0x6a1F…A4A` v1, `0xa6C9…df0` v2)
  are thin proxies/modules that emit **no logs**.
- Tracing a real job memo's `txHash` shows ACP jobs settle through the
  ERC-4337 EntryPoint (`0x0000000071727De22E5E9d8BAf0edAc6f37da032`), with ACP
  events emitted by **`0x9c6C5A7125934CC6A711A7Bf44f3cDcCcf91F30c`** —
  confirmed live (29 events in ~2.8 h on 2026-07-03; dominant topic
  `0xbb0268ad…`). ABIs are in the SDK repo (`virtuals_acp/abis/`).
- Feasible but strictly harder than Route 1: event decoding + 4337 unwrapping
  + slow `eth_getLogs` scans on the public RPC (`https://mainnet.base.org`,
  verified working read-only). No job *content* on chain — only lifecycle.
- **Use**: spot-verify the `txHash` evidence embedded in Route 1 memos
  (receipt exists, emitter is the ACP contract, block time matches). This
  gives on-chain-anchored provenance without full indexing.

## Route 3 — Indexers: **EXISTS, INFERIOR**

- [Dune: Virtuals ACP dashboard](https://dune.com/hashed_official/acp-virtuals)
  — aggregate protocol metrics; programmatic access needs a paid Dune API key;
  provenance is third-party SQL. Not needed given Route 1.
- No public subgraph found for ACP job data.

## Deviations from SPEC assumptions

1. **Ethy AI (default target, §8.1) was not found** in agent search
   (`search=ethy`, `search=Ethy AI`). High-volume alternatives observed:
   Luna (40,160 successful jobs), Otto AI (29,991), Arbus (3,461, 87.9%
   success rate). **Operator must confirm the Phase 2 target.** Arbus was used
   for the Phase 0 cache.
2. **~5% of jobs are not USDC-priced** (185/3,404 in the Arbus pull);
   `price_usd` is NULL for those (raw token amount preserved in `raw_json`).
   A conversion rule (which price feed, at what timestamp) is an operator
   decision before Phase 1 regime classification; simplest defensible option:
   classify non-USDC jobs by converting at pull time using a fixed public feed,
   or exclude them from Regime A (they are a small minority).
3. `GET /jobs/cancelled` covers both REJECTED and EXPIRED phases — mapped to
   distinct `status` values in the cache.

## Cache summary (data/acp.db)

- Agent: Arbus `0xe502bab730bf3403e944f132b23ee5f1c2ceb653`
- 3,404 jobs: 2,000 COMPLETED (of 3,461 total, capped), 838 EXPIRED,
  566 REJECTED · 2025-06-26 → 2026-03-31
- 3,219 with USD price (min $1e-12, max $2.00, mean $1.20)
- `raw_json` verbatim for every row; `make test-data` verifies every cached
  column is byte-identical when re-derived from `raw_json` alone.
- Pull provenance in `pulls` table (source, timestamp, params).
