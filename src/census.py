"""Census / Gate 0 report (SPEC §4 Phase 1) → reports/census_report.md.

Deterministic: derived entirely from the cache + config; no wall-clock reads,
so re-running on the same cache produces a byte-identical report.
"""

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from src.classify import CONFIG_PATH, classify_all, load_config
from src.db import connect

REPORT_PATH = Path(__file__).resolve().parent.parent / "reports" / "census_report.md"

PRICE_BUCKETS = [(0, 0.01), (0.01, 0.1), (0.1, 1), (1, 5), (5, 50), (50, float("inf"))]


def config_hash() -> str:
    return hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()[:16]


def fmt_bucket(lo, hi):
    return f"${lo}–${hi}" if hi != float("inf") else f">${lo}"


def build_report() -> str:
    conn = connect()
    cfg = load_config()
    jobs = classify_all(conn, cfg)

    agents = {a: n for a, n in conn.execute(
        "SELECT agent_id, name FROM agents ORDER BY agent_id")}
    date_lo, date_hi = conn.execute(
        "SELECT MIN(ts_request), MAX(ts_request) FROM jobs").fetchone()
    pulls = conn.execute(
        "SELECT source, agent_id, pulled_at, n_records FROM pulls "
        "ORDER BY pull_id").fetchall()

    statuses = Counter(j["status"] for j in jobs)
    regimes = Counter(j["regime"] for j in jobs)
    n = len(jobs)

    priced = [j for j in jobs if j["price_usd"] is not None]
    buckets = Counter()
    for j in priced:
        for lo, hi in PRICE_BUCKETS:
            if lo <= j["price_usd"] < hi or (hi == float("inf") and j["price_usd"] >= lo):
                buckets[(lo, hi)] += 1
                break

    types = Counter((j["agent_id"], j["job_type"]) for j in jobs)
    completed_by_agent = Counter(
        j["agent_id"] for j in jobs if j["status"] == "COMPLETED")

    regime_by_agent = defaultdict(Counter)
    for j in jobs:
        regime_by_agent[j["agent_id"]][j["regime"]] += 1

    L = []
    L.append("# ACP Market Census — Gate 0\n")
    L.append("## Provenance\n")
    L.append("| | |\n|---|---|")
    L.append("| Data source | official Virtuals ACP API (`https://acpx.virtuals.io/api`) |")
    L.append(f"| Job date range | {date_lo} → {date_hi} |")
    L.append(f"| Agents cached | {len(agents)} |")
    L.append(f"| Seed | {cfg['seed']} |")
    L.append(f"| Config hash | `{config_hash()}` |")
    L.append("\nPulls:\n")
    L.append("| pulled_at (UTC) | agent | records |\n|---|---|---|")
    for src, aid, ts, nr in pulls:
        L.append(f"| {ts} | {agents.get(aid, aid)} | {nr} |")

    L.append("\n## Totals\n")
    L.append(f"- **{n} jobs** across **{len(agents)} agents**")
    L.append("- Status: " + ", ".join(
        f"{k} {v} ({100*v/n:.1f}%)" for k, v in statuses.most_common()))

    L.append("\n## Regime split (SPEC §2 rules; classifier v0)\n")
    L.append("| Regime | Jobs | % |\n|---|---|---|")
    for r in ("A", "B", "EXCLUDED"):
        L.append(f"| {r} | {regimes.get(r, 0)} | {100*regimes.get(r, 0)/n:.1f}% |")
    L.append("\nEXCLUDED = non-USDC pricing (operator decision 2026-07-03). "
             "Verification mode defaults to instant/deterministic pending "
             "golden-set calibration (see src/classify.py).")

    L.append("\n## Value distribution (USD-priced jobs)\n")
    L.append("| Price | Jobs | % of priced |\n|---|---|---|")
    for lo, hi in PRICE_BUCKETS:
        c = buckets.get((lo, hi), 0)
        L.append(f"| {fmt_bucket(lo, hi)} | {c} | {100*c/len(priced):.1f}% |")

    L.append("\n## Job types (top 15 by volume)\n")
    L.append("| Agent | Job type | Jobs |\n|---|---|---|")
    for (aid, jtype), c in types.most_common(15):
        L.append(f"| {agents.get(aid, aid)} | {jtype or '—'} | {c} |")

    L.append("\n## Agents by completed volume (cached)\n")
    L.append("| Agent | Completed | Cached total | A | B | EXCLUDED |\n|---|---|---|---|---|---|")
    for aid, c in completed_by_agent.most_common():
        rb = regime_by_agent[aid]
        total = sum(rb.values())
        L.append(f"| {agents.get(aid, aid)} | {c} | {total} "
                 f"| {rb.get('A', 0)} | {rb.get('B', 0)} | {rb.get('EXCLUDED', 0)} |")

    L.append("\n*Note: per-agent counts reflect the cache (pulls capped at "
             "2,000 jobs per status), not lifetime registry totals.*\n")
    return "\n".join(L)


def main() -> None:
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(build_report())
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
