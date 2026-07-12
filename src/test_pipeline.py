"""Phase 2 acceptance checks (`make test-pipeline`, SPEC §9 row 2).

1. Reproducibility: two assessment runs on the same cache + seed give
   identical composite and subscores.
2. Judge stability: 3 passes on the 20-job golden set at temperature 0,
   per-item spread <= ±0.5 (i.e. max-min <= 1.0).
3. Calibration: Spearman(judge, operator) >= 0.7 when operator scores exist
   in golden/judge_candidates.csv. Pending scores is reported, not failed.
"""

import csv
import json
import sys
from pathlib import Path

import pandas as pd

from src.assess import run_assessment
from src.classify import load_config
from src.db import connect
from src.judge import Judge, judge_input
from src.judge_golden import golden_job_ids

GOLDEN_CSV = Path(__file__).resolve().parent.parent / "golden" / "judge_candidates.csv"
SCORE_KEYS = ("completion", "conformance", "evidence", "latency", "composite")


def main() -> None:
    conn = connect()
    cfg = load_config()
    failures = []

    r1 = run_assessment(conn, cfg["default_agent"], cfg)
    r2 = run_assessment(conn, cfg["default_agent"], cfg)
    same = all(r1[k] == r2[k] for k in SCORE_KEYS)
    print(f"reproducibility: run1 composite={r1['composite']} "
          f"run2 composite={r2['composite']} identical={same}")
    print(f"  (run2 judge api calls: {r2['judge_api_calls']} — expect 0, all cached)")
    if not same:
        failures.append("two runs differ")
    if r2["judge_api_calls"] != 0:
        failures.append("second run hit the API; cache incomplete")

    judge = Judge(conn, cfg)
    agent_names = [n for (n,) in conn.execute(
        "SELECT name FROM agents WHERE name IS NOT NULL")]
    per_item = {}
    for jid in golden_job_ids(conn, cfg):
        raw = json.loads(conn.execute(
            "SELECT raw_json FROM jobs WHERE job_id=?", (jid,)).fetchone()[0])
        prompt = judge_input(raw, agent_names)
        scores = [judge.score(jid, prompt, pass_n=p)["score"] for p in (1, 2, 3)]
        per_item[jid] = scores
    spreads = {j: max(s) - min(s) for j, s in per_item.items()
               if all(x is not None for x in s)}
    worst = max(spreads.values()) if spreads else None
    print(f"judge stability: {len(per_item)} items x 3 passes, "
          f"max per-item spread = {worst} (require <= 1.0, i.e. ±0.5)")
    print(f"  stability judge cost this run: ${judge.run_cost:.2f} "
          f"({judge.api_calls} api calls)")
    if worst is None or worst > 1.0:
        failures.append(f"judge stability spread {worst} > 1.0")
    if len(spreads) < len(per_item):
        failures.append("unparseable judge scores in stability passes")

    ops = {}
    if GOLDEN_CSV.exists():
        for row in csv.DictReader(open(GOLDEN_CSV)):
            v = (row.get("operator_score") or "").strip()
            if v:
                ops[row["job_id"]] = float(v)
    if ops:
        pairs = [(sum(s) / len(s), ops[j]) for j, s in per_item.items()
                 if j in ops and all(x is not None for x in s)]
        df = pd.DataFrame(pairs, columns=["judge", "operator"])
        rho = df["judge"].corr(df["operator"], method="spearman")
        print(f"calibration: Spearman={rho:.3f} over {len(pairs)} items "
              f"(require >= 0.7)")
        if rho < 0.7:
            failures.append(f"Spearman {rho:.3f} < 0.7 — iterate rubric")
    else:
        print("calibration: PENDING — no operator scores in "
              "golden/judge_candidates.csv")

    if failures:
        for x in failures:
            print(f"FAIL: {x}")
        sys.exit(1)
    print("PASS: Phase 2 pipeline acceptance checks"
          + (" (calibration pending operator scores)" if not ops else ""))


if __name__ == "__main__":
    main()
