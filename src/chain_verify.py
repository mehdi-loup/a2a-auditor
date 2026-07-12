"""On-chain spot-verification of job settlement evidence (V2 support).

For each sampled job, verify that at least one memo txHash resolves to a
successful Base receipt whose logs include the ACP event contract. Results are
cached in chain_checks so re-runs read the cache (deterministic, no RPC).
"""

import json
import os

from web3 import Web3

ACP_EVENT_CONTRACT = "0x9c6c5a7125934cc6a711a7bf44f3cdcccf91f30c"

SCHEMA = """
CREATE TABLE IF NOT EXISTS chain_checks (
    tx_hash    TEXT PRIMARY KEY,
    found      INTEGER,
    status     INTEGER,
    acp_emitter INTEGER,
    block_number INTEGER
);
"""


class ChainVerifier:
    def __init__(self, conn):
        self.conn = conn
        conn.executescript(SCHEMA)
        self._w3 = None
        self.rpc_calls = 0

    @property
    def w3(self):
        if self._w3 is None:
            from src.envfile import load_env
            load_env()
            url = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
            self._w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
        return self._w3

    def check_tx(self, tx_hash: str) -> dict:
        row = self.conn.execute(
            "SELECT found, status, acp_emitter FROM chain_checks WHERE tx_hash=?",
            (tx_hash,)).fetchone()
        if row is not None:
            return {"found": bool(row[0]), "status": row[1],
                    "acp_emitter": bool(row[2]), "cached": True}
        try:
            r = self.w3.eth.get_transaction_receipt(tx_hash)
            self.rpc_calls += 1
            emitters = {l["address"].lower() for l in r["logs"]}
            vals = (1, r["status"], int(ACP_EVENT_CONTRACT in emitters),
                    r["blockNumber"])
        except Exception:
            self.rpc_calls += 1
            vals = (0, None, 0, None)
        self.conn.execute(
            "INSERT OR REPLACE INTO chain_checks VALUES (?,?,?,?,?)",
            (tx_hash, *vals))
        self.conn.commit()
        return {"found": bool(vals[0]), "status": vals[1],
                "acp_emitter": bool(vals[2]), "cached": False}

    def verify_job(self, raw: dict) -> dict:
        """True if any memo tx settles on-chain via the ACP contract."""
        hashes = []
        for m in raw.get("memos") or []:
            for k in ("txHash", "signedTxHash"):
                h = m.get(k)
                if h and h.startswith("0x") and len(h) == 66:
                    hashes.append(h)
        if not hashes:
            return {"has_evidence": False, "verified": False}
        for h in sorted(set(hashes)):
            c = self.check_tx(h)
            if c["found"] and c["status"] == 1 and c["acp_emitter"]:
                return {"has_evidence": True, "verified": True}
        return {"has_evidence": True, "verified": False}
