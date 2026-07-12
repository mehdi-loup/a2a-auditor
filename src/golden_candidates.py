"""Surface 50 classifier golden-set candidates for operator labeling.

Seeded sample (seed from config.yaml) stratified across agents and regimes so
labels exercise the classifier's boundaries. Writes
golden/classifier_candidates.csv with an empty operator_label column
(fill with A / B / EXCLUDED).
"""

import csv
import json
import random
from pathlib import Path

from src.classify import classify_all, load_config
from src.db import connect

OUT = Path(__file__).resolve().parent.parent / "golden" / "classifier_candidates.csv"
N = 50


def summarize_job(conn, job_id: str) -> tuple[str, str]:
    raw = json.loads(conn.execute(
        "SELECT raw_json FROM jobs WHERE job_id = ?", (job_id,)).fetchone()[0])
    req = ""
    for m in raw.get("memos") or []:
        if m.get("type") == "REQUEST_JOB":
            req = m.get("content") or ""
            break
    deliv = raw.get("deliverable")
    deliv = json.dumps(deliv) if isinstance(deliv, dict) else (deliv or "")
    clean = lambda s: " ".join(str(s).split())[:300]
    return clean(req), clean(deliv)


def main() -> None:
    conn = connect()
    cfg = load_config()
    jobs = classify_all(conn, cfg)
    rng = random.Random(cfg["seed"])

    # Stratify: proportional across (agent, regime) cells, at least 1 per cell
    # where possible, deterministic order.
    cells: dict[tuple, list[dict]] = {}
    for j in jobs:
        cells.setdefault((j["agent_id"], j["regime"]), []).append(j)
    picked = []
    cell_keys = sorted(cells)
    for key in cell_keys:
        pool = cells[key]
        share = max(1, round(N * len(pool) / len(jobs)))
        picked.extend(rng.sample(pool, min(share, len(pool))))
    rng.shuffle(picked)
    picked = picked[:N]

    agents = dict(conn.execute("SELECT agent_id, name FROM agents"))
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["job_id", "agent", "job_type", "status", "price_usd",
                    "duration_s", "request_summary", "deliverable_summary",
                    "classifier_regime", "classifier_reasons", "operator_label"])
        for j in sorted(picked, key=lambda x: x["job_id"]):
            req, deliv = summarize_job(conn, j["job_id"])
            w.writerow([j["job_id"], agents.get(j["agent_id"], j["agent_id"]),
                        j["job_type"], j["status"], j["price_usd"],
                        j["duration_s"], req, deliv,
                        j["regime"], j["reasons"], ""])
    print(f"wrote {OUT} ({len(picked)} candidates)")


if __name__ == "__main__":
    main()
