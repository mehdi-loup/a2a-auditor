"""Seeded job sampling for assessments (SPEC §4 Phase 2).

n = min(200, 10% of the agent's jobs in the last 60 days). The 60-day window
is anchored to the newest cached job for that agent — not the wall clock — so
identical cache + seed => identical sample regardless of when the run happens.
"""

import random
from datetime import timedelta

from src.classify import _parse_ts, load_config


def sample_jobs(conn, agent_id: str, config: dict = None) -> list[str]:
    cfg = config or load_config()
    rows = conn.execute(
        "SELECT job_id, ts_request FROM jobs WHERE agent_id = ? "
        "ORDER BY job_id", (agent_id.lower(),)).fetchall()
    if not rows:
        raise SystemExit(f"no cached jobs for agent {agent_id}")

    anchor = max(_parse_ts(ts) for _, ts in rows if _parse_ts(ts))
    cutoff = anchor - timedelta(days=cfg["window_days"])
    window = [jid for jid, ts in rows
              if _parse_ts(ts) and _parse_ts(ts) >= cutoff]

    n = min(200, max(1, len(window) // 10))
    rng = random.Random(cfg["seed"])
    return sorted(rng.sample(window, min(n, len(window))))
