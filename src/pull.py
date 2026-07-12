"""Pull and cache ACP job history for one agent from the official Virtuals API.

Source: https://acpx.virtuals.io/api (endpoints discovered from the
Virtual-Protocol/acp-python SDK; see FINDINGS.md). Read-only GETs, no auth.
Raw responses are preserved verbatim in jobs.raw_json (SPEC §6).

Usage: python -m src.pull <agent name or 0xWalletAddress>
"""

import json
import sys
import time
from datetime import datetime, timezone

import requests

from src.db import connect

API = "https://acpx.virtuals.io/api"
USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
PAGE_SIZE = 100
MAX_JOBS_PER_STATUS = 2000

PHASE_STATUS = {
    0: "REQUEST", 1: "NEGOTIATION", 2: "TRANSACTION", 3: "EVALUATION",
    4: "COMPLETED", 5: "REJECTED", 6: "EXPIRED",
}


def find_agent(query: str) -> dict:
    if query.startswith("0x"):
        # Search API has no wallet lookup; caller passes name for metadata.
        return {"walletAddress": query, "name": query, "id": None}
    r = requests.get(f"{API}/agents/v4/search",
                     params={"search": query, "top_k": 10}, timeout=30)
    r.raise_for_status()
    candidates = r.json()["data"]
    if not candidates:
        raise SystemExit(f"no agent found for {query!r}")
    exact = [a for a in candidates if a["name"].lower() == query.lower()]
    agent = exact[0] if exact else candidates[0]
    if not exact:
        print(f"no exact name match; using top result {agent['name']!r} "
              f"({agent['walletAddress']})")
    return agent


def fetch_jobs(wallet: str, status: str):
    page = 1
    while True:
        r = requests.get(
            f"{API}/jobs/{status}",
            params={"pagination[page]": page, "pagination[pageSize]": PAGE_SIZE},
            headers={"wallet-address": wallet},
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        jobs = body.get("data", [])
        if not jobs:
            return
        for j in jobs:
            yield j
        total = body.get("meta", {}).get("pagination", {}).get("pageCount", page)
        if page >= total or page * PAGE_SIZE >= MAX_JOBS_PER_STATUS:
            return
        page += 1
        time.sleep(0.5)


def job_row(j: dict, wallet: str) -> tuple:
    memos = j.get("memos") or []
    request_memo = next((m for m in memos if m.get("type") == "REQUEST_JOB"), None)
    job_type = None
    if request_memo:
        try:
            job_type = json.loads(request_memo["content"]).get("name")
        except (ValueError, TypeError, KeyError):
            pass
    if not job_type and isinstance(j.get("deliverable"), dict):
        job_type = j["deliverable"].get("service_name")

    price_usd = None
    token = (j.get("priceTokenAddress") or "").lower()
    if token == USDC_BASE:
        price_usd = j.get("price")

    evidence = [
        {"memo_id": m.get("id"), "type": m.get("type"),
         "txHash": m.get("txHash"), "signedTxHash": m.get("signedTxHash")}
        for m in memos if m.get("txHash") or m.get("signedTxHash")
    ]

    # Delivery timestamp: OBJECT_URL/deliverable memo if present, else
    # updatedAt for completed jobs.
    delivery_memo = next(
        (m for m in memos if m.get("nextPhase") == 3 or m.get("type") == "OBJECT_URL"),
        None)
    ts_delivery = (delivery_memo or {}).get("createdAt")
    if not ts_delivery and j.get("phase") == 4:
        ts_delivery = j.get("updatedAt")

    return (
        str(j["id"]),
        (j.get("providerAddress") or wallet).lower(),
        (j.get("clientAddress") or "").lower(),
        j.get("createdAt"),
        ts_delivery,
        job_type,
        price_usd,
        None,  # request_uri: request content is inline in raw_json
        None,  # deliverable_uri: deliverable is inline in raw_json
        PHASE_STATUS.get(j.get("phase"), f"PHASE_{j.get('phase')}"),
        json.dumps(evidence, sort_keys=True),
        json.dumps(j, sort_keys=True),
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m src.pull <agent name or 0xWallet>")
    query = " ".join(sys.argv[1:])
    agent = find_agent(query)
    wallet = agent["walletAddress"].lower()

    conn = connect()
    pulled_at = datetime.now(timezone.utc).isoformat()
    n = 0
    for status in ("completed", "cancelled"):
        for j in fetch_jobs(agent["walletAddress"], status):
            conn.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                job_row(j, wallet))
            n += 1
        conn.commit()
        print(f"{status}: cumulative {n} jobs cached")

    total_jobs = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE agent_id = ?", (wallet,)).fetchone()[0]
    conn.execute(
        "INSERT OR REPLACE INTO agents VALUES (?,?,?,?,?)",
        (wallet, agent.get("name"), json.dumps({"api": API}),
         pulled_at, total_jobs))
    conn.execute(
        "INSERT INTO pulls (source, agent_id, pulled_at, params_json, n_records) "
        "VALUES (?,?,?,?,?)",
        (API, wallet, pulled_at,
         json.dumps({"query": query, "page_size": PAGE_SIZE,
                     "max_per_status": MAX_JOBS_PER_STATUS}), n))
    conn.commit()
    print(f"done: {n} jobs pulled for {agent.get('name')} ({wallet}), "
          f"{total_jobs} total cached for this agent")


if __name__ == "__main__":
    main()
