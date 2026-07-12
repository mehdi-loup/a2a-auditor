"""Assessment report generator (SPEC §4 Phase 3).

`make assess AGENT=<id>` → reports/<agent>_<date>.md. Runs the full pipeline
from cache (judge/chain results cached => no API calls on re-runs) and renders
the private report. Deterministic: the filename date and every number derive
from the cache, not the wall clock — re-running produces a byte-identical
file.
"""

import json
import sys
from pathlib import Path

from src.assess import config_hash, resolve_agent, run_assessment
from src.classify import load_config
from src.db import connect
from src.judge import strip_identity

REPORTS = Path(__file__).resolve().parent.parent / "reports"


def failure_examples(conn, agent_id: str, agent_names: list[str], k: int = 3):
    """Deterministic pick: worst-judged delivered jobs, then non-delivered."""
    rows = conn.execute(
        "SELECT job_id, delivered, judge_score, judge_reason FROM assessment_jobs "
        "WHERE agent_id=? ORDER BY delivered DESC, judge_score ASC, job_id",
        (agent_id,)).fetchall()
    picked = [r for r in rows if r[1] and r[2] is not None and r[2] <= 6][:2]
    picked += [r for r in rows if not r[1]][: k - len(picked)]

    out = []
    for job_id, delivered, score, reason in picked[:k]:
        status, raw = conn.execute(
            "SELECT status, raw_json FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        raw = json.loads(raw)
        req = ""
        for m in raw.get("memos") or []:
            if m.get("type") == "REQUEST_JOB":
                req = m.get("content") or ""
                break
        req = strip_identity(" ".join(req.split()), agent_names)[:220]
        if delivered:
            desc = f"judge {score}/10 — {reason}"
        else:
            desc = f"not delivered (status {status})"
        out.append((req, desc))
    return out


def render(conn, agent_query: str) -> Path:
    cfg = load_config()
    res = run_assessment(conn, agent_query, cfg)
    agent_id = res["agent_id"]
    agent_names = [n for (n,) in conn.execute(
        "SELECT name FROM agents WHERE name IS NOT NULL")]
    name = conn.execute(
        "SELECT name FROM agents WHERE agent_id=?", (agent_id,)).fetchone()[0]

    row = conn.execute(
        "SELECT window_start, window_end FROM assessments WHERE agent_id=? "
        "AND seed=? AND config_hash=?",
        (agent_id, cfg["seed"], config_hash())).fetchone()
    window_start, window_end = row
    pulls = conn.execute(
        "SELECT pulled_at, n_records FROM pulls WHERE agent_id=? "
        "ORDER BY pull_id", (agent_id,)).fetchall()
    date_lo, date_hi = conn.execute(
        "SELECT MIN(ts_request), MAX(ts_request) FROM jobs WHERE agent_id=?",
        (agent_id,)).fetchone()

    w = cfg["weights"]
    L = []
    L.append(f"# Reliability Assessment — {name}\n")
    L.append(f"Agent wallet: `{agent_id}` · Regime A scope\n")
    L.append("## Methodology\n")
    L.append(
        "A seeded random sample of the agent's jobs from the assessment window "
        "was verified on four dimensions: completion (delivered vs failed), "
        "conformance (LLM judge, deliverable vs request, agent identity "
        "hidden), settlement evidence (on-chain receipt verification on "
        "Base), and latency (vs the agent's own job-type medians). The "
        "composite is a weighted sum of the four subscores; weights are "
        "provisional v0 values stated below.\n")
    L.append("## Window & sample\n")
    L.append("| | |\n|---|---|")
    L.append(f"| Sampling window | {window_start} → {window_end} "
             f"(last {cfg['window_days']} days of observed activity) |")
    L.append(f"| Jobs sampled | {res['n_sampled']} "
             f"(n = min(200, 10% of window)) |")
    L.append(f"| Delivered in sample | {res['n_delivered']} |")
    L.append("\n## Scores\n")
    L.append("| Dimension | Weight | Subscore (0–100) |\n|---|---|---|")
    L.append(f"| Completion | {w['completion']:.2f} | {res['completion']} |")
    L.append(f"| Conformance | {w['conformance']:.2f} | {res['conformance']} |")
    L.append(f"| Evidence | {w['evidence']:.2f} | {res['evidence']} |")
    L.append(f"| Latency | {w['latency']:.2f} | {res['latency']} |")
    L.append(f"| **Composite** | | **{res['composite']}** |")
    L.append("\nSubscore definitions: completion = delivered/sampled; "
             "conformance = mean judge score (0–10, scaled); evidence = "
             "delivered jobs with an on-chain-verified settlement tx; latency "
             "= delivered jobs within 2× their job-type median duration.")

    L.append("\n## Failure examples (anonymized)\n")
    for i, (req, desc) in enumerate(failure_examples(conn, agent_id, agent_names), 1):
        L.append(f"{i}. Request: “{req}…”")
        L.append(f"   Outcome: {desc}\n")

    L.append("## Provenance\n")
    L.append("| | |\n|---|---|")
    L.append("| Data source | official Virtuals ACP API (`https://acpx.virtuals.io/api`) |")
    L.append("| Settlement verification | Base mainnet RPC, read-only; ACP event "
             "contract `0x9c6C5A7125934CC6A711A7Bf44f3cDcCcf91F30c` |")
    L.append(f"| Cached job range (this agent) | {date_lo} → {date_hi} |")
    for ts, nr in pulls:
        L.append(f"| Pull | {ts} ({nr} records) |")
    L.append(f"| Seed | {cfg['seed']} |")
    L.append(f"| Config hash | `{config_hash()}` |")
    L.append(f"| Judge | {cfg['judge']['model']}, temperature 0, rubric v0.1 |")
    L.append("\n---\n**Private assessment — not for distribution.**\n")

    slug = (name or agent_id).lower().split(" ")[0].replace("/", "-")
    out = REPORTS / f"{slug}_{window_end[:10]}.md"
    out.write_text("\n".join(L))
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m src.report <agent>")
    conn = connect()
    out = render(conn, " ".join(sys.argv[1:]))
    print(f"wrote {out}")
    # Optional PDF render when pandoc is available (SPEC: optional).
    import shutil, subprocess
    if shutil.which("pandoc"):
        pdf = out.with_suffix(".pdf")
        try:
            subprocess.run(["pandoc", str(out), "-o", str(pdf)],
                           check=True, capture_output=True)
            print(f"wrote {pdf}")
        except subprocess.CalledProcessError as e:
            print(f"pandoc render skipped: {e.stderr.decode()[:200]}")


if __name__ == "__main__":
    main()
