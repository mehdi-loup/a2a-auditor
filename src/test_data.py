"""Phase 0 acceptance checks (`make test-data`, SPEC §9 row 0).

Verifies the cache satisfies Phase 0: >=500 jobs for at least one agent,
raw_json preserved verbatim and parseable, and cached columns re-derivable
from raw_json alone.
"""

import json
import sys

from src.db import connect
from src.pull import job_row


def main() -> None:
    conn = connect()
    failures = []

    counts = conn.execute(
        "SELECT agent_id, COUNT(*) FROM jobs GROUP BY agent_id").fetchall()
    best = max((n for _, n in counts), default=0)
    print(f"agents cached: {len(counts)}; max jobs for one agent: {best}")
    if best < 500:
        failures.append("need >=500 jobs for at least one agent")

    rows = conn.execute(
        "SELECT job_id, agent_id, status, price_usd, ts_request, raw_json "
        "FROM jobs").fetchall()
    n_bad_json = n_no_ts = 0
    for job_id, agent_id, status, price_usd, ts_request, raw in rows:
        try:
            j = json.loads(raw)
        except ValueError:
            n_bad_json += 1
            continue
        rederived = job_row(j, agent_id)
        cached = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if tuple(cached) != rederived:
            failures.append(f"job {job_id}: cached row != re-derived from raw_json")
            break
        if not ts_request:
            n_no_ts += 1
    print(f"jobs checked: {len(rows)}; unparseable raw_json: {n_bad_json}; "
          f"missing ts_request: {n_no_ts}")
    if n_bad_json:
        failures.append(f"{n_bad_json} rows with unparseable raw_json")

    n_priced = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE price_usd IS NOT NULL").fetchone()[0]
    print(f"jobs with USD (USDC) price: {n_priced}/{len(rows)}")

    pulls = conn.execute("SELECT COUNT(*) FROM pulls").fetchone()[0]
    if pulls == 0:
        failures.append("no pull provenance recorded")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        sys.exit(1)
    print("PASS: Phase 0 data acceptance checks")


if __name__ == "__main__":
    main()
