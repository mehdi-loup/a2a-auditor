"""Phase 1 acceptance checks (`make test-census`, SPEC §9 row 1).

1. >=1,000 jobs classified across >=5 agents (or state the constraint).
2. Census + classification deterministic: two runs -> byte-identical report.
3. Classifier vs operator golden labels >=90% agreement, when labels exist
   (golden/classifier_labels.csv or filled operator_label column in
   golden/classifier_candidates.csv). Pending labels is reported, not failed.
"""

import csv
import sys
from pathlib import Path

from src.census import build_report
from src.classify import classify_all
from src.db import connect

GOLDEN = Path(__file__).resolve().parent.parent / "golden"


def load_labels() -> dict[str, str]:
    labels = {}
    for name in ("classifier_labels.csv", "classifier_candidates.csv"):
        p = GOLDEN / name
        if not p.exists():
            continue
        with open(p, newline="") as f:
            for row in csv.DictReader(f):
                lab = (row.get("operator_label") or "").strip().upper()
                if lab:
                    labels[row["job_id"]] = lab
        if labels:
            break
    return labels


def main() -> None:
    conn = connect()
    failures = []

    jobs = classify_all(conn)
    agents = {j["agent_id"] for j in jobs}
    print(f"classified {len(jobs)} jobs across {len(agents)} agents")
    if len(jobs) < 1000:
        failures.append("need >=1,000 classified jobs")
    if len(agents) < 5:
        failures.append("need >=5 agents")

    r1, r2 = build_report(), build_report()
    print(f"determinism: two census runs identical = {r1 == r2}")
    if r1 != r2:
        failures.append("census output not deterministic")

    labels = load_labels()
    if labels:
        by_id = {j["job_id"]: j["regime"] for j in jobs}
        scored = [(jid, lab) for jid, lab in labels.items() if jid in by_id]
        agree = sum(1 for jid, lab in scored if by_id[jid] == lab)
        pct = 100 * agree / len(scored) if scored else 0
        print(f"golden agreement: {agree}/{len(scored)} = {pct:.1f}%")
        if pct < 90:
            failures.append(f"golden agreement {pct:.1f}% < 90%")
    else:
        print("golden agreement: PENDING — no operator labels yet "
              "(fill operator_label in golden/classifier_candidates.csv)")

    if failures:
        for x in failures:
            print(f"FAIL: {x}")
        sys.exit(1)
    print("PASS: Phase 1 census acceptance checks"
          + (" (golden agreement pending labels)" if not labels else ""))


if __name__ == "__main__":
    main()
