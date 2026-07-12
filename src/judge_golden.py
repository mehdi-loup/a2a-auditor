"""Judge golden set: 20 delivered jobs sampled across ALL cached agents
(stratified ~equally per agent) so calibration covers diverse job types.
Drawn agent-by-agent rather than from one assessment sample because the
default target's 60-day window turned out to be thin (see PHASE_REPORT).

Writes golden/judge_candidates.csv for operator scoring (0-10 conformance,
column operator_score). Also used by test_pipeline for the 3-pass stability
check.
"""

import csv
import json
import random
from pathlib import Path

from src.classify import load_config
from src.db import connect
from src.judge import judge_input

OUT = Path(__file__).resolve().parent.parent / "golden" / "judge_candidates.csv"
N = 20


def golden_job_ids(conn, cfg=None) -> list[str]:
    cfg = cfg or load_config()
    agent_names = [n for (n,) in conn.execute(
        "SELECT name FROM agents WHERE name IS NOT NULL")]
    by_agent: dict[str, list[str]] = {}
    for jid, aid, raw in conn.execute(
            "SELECT job_id, agent_id, raw_json FROM jobs "
            "WHERE status='COMPLETED' ORDER BY job_id"):
        if judge_input(json.loads(raw), agent_names):
            by_agent.setdefault(aid, []).append(jid)

    rng = random.Random(cfg["seed"] + 1)  # distinct stream from the sampler
    picked: list[str] = []
    agents = sorted(by_agent)
    quota = max(1, N // len(agents)) if agents else 0
    for aid in agents:
        picked.extend(rng.sample(by_agent[aid], min(quota, len(by_agent[aid]))))
    # top up to N from the remaining pool, deterministically
    rest = sorted(set(j for pool in by_agent.values() for j in pool) - set(picked))
    if len(picked) < N and rest:
        picked.extend(rng.sample(rest, min(N - len(picked), len(rest))))
    return sorted(picked[:N])


def main() -> None:
    conn = connect()
    cfg = load_config()
    agent_names = [n for (n,) in conn.execute(
        "SELECT name FROM agents WHERE name IS NOT NULL")]
    clean = lambda s: " ".join(str(s).split())
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["job_id", "job_type", "request", "deliverable",
                    "proposed_score", "proposal_rationale", "operator_score"])
        for jid in golden_job_ids(conn, cfg):
            jtype, raw = conn.execute(
                "SELECT job_type, raw_json FROM jobs WHERE job_id=?",
                (jid,)).fetchone()
            raw = json.loads(raw)
            prompt = judge_input(raw, agent_names)
            req, _, deliv = prompt.partition("</job_request>")
            req = clean(req.replace("<job_request>", ""))[:800]
            deliv = clean(deliv.replace("<deliverable>", "")
                          .replace("</deliverable>", ""))[:800]
            w.writerow([jid, jtype, req, deliv, "", "", ""])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
