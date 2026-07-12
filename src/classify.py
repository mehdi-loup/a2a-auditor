"""Regime A/B classifier v0 (SPEC §2). Pure functions over the cache.

Rules, in order:
  EXCLUDED  price_usd is NULL (non-USDC pricing; operator decision 2026-07-03)
  B         price_usd > max_price_usd
  B         duration > max_duration_seconds (measured for delivered jobs;
            job-type median for the same agent otherwise)
  A         everything else

Verification-mode rationale: ACP jobs settle on-chain with the deliverable
returned inline and checked at delivery time, so verification is treated as
instant/deterministic by default in v0. Price and duration are the operative
criteria. The 50-job golden set calibrates this assumption; if operator labels
disagree ≥10%, the rule set is revised before Phase 2.
"""

from datetime import datetime
from pathlib import Path
from statistics import median

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _parse_ts(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_seconds(ts_request: str, ts_delivery: str):
    a, b = _parse_ts(ts_request), _parse_ts(ts_delivery)
    if a is None or b is None:
        return None
    return (b - a).total_seconds()


def classify_all(conn, config: dict = None) -> list[dict]:
    """Classify every cached job. Deterministic: ordered by job_id."""
    cfg = (config or load_config())["regime_a"]
    max_price = cfg["max_price_usd"]
    max_dur = cfg["max_duration_seconds"]

    rows = conn.execute(
        "SELECT job_id, agent_id, job_type, price_usd, ts_request, ts_delivery,"
        " status FROM jobs ORDER BY job_id").fetchall()

    # Job-type median durations from delivered jobs (fallback for undelivered).
    by_type: dict[tuple, list[float]] = {}
    for job_id, agent, jtype, price, ts_req, ts_del, status in rows:
        d = duration_seconds(ts_req, ts_del)
        if d is not None and d >= 0:
            by_type.setdefault((agent, jtype), []).append(d)
    type_median = {k: median(sorted(v)) for k, v in by_type.items()}

    out = []
    for job_id, agent, jtype, price, ts_req, ts_del, status in rows:
        reasons = []
        dur = duration_seconds(ts_req, ts_del)
        dur_basis = "measured"
        if dur is None or dur < 0:
            dur = type_median.get((agent, jtype))
            dur_basis = "job_type_median" if dur is not None else "unknown"

        if price is None:
            regime = "EXCLUDED"
            reasons.append("non-USD pricing (operator exclusion)")
        else:
            if price > max_price:
                reasons.append(f"price {price} > {max_price}")
            if dur is not None and dur > max_dur:
                reasons.append(f"duration {dur:.0f}s > {max_dur}s ({dur_basis})")
            regime = "B" if reasons else "A"

        out.append({
            "job_id": job_id, "agent_id": agent, "job_type": jtype,
            "price_usd": price, "status": status,
            "duration_s": dur, "duration_basis": dur_basis,
            "regime": regime, "reasons": "; ".join(reasons),
        })
    return out
