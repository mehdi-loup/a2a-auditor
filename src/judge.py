"""LLM conformance judge (SPEC §7). V3 of the verification checks.

- Model + temperature 0 + budget cap from config.yaml.
- Agent identity (name, wallet addresses) stripped from judge inputs.
- Every response cached in judge_scores keyed by (job_id, prompt_sha, pass_n):
  re-runs on the same cache never call the API, so scores are re-derivable
  and re-runs are free.
- Budget guard: cumulative per-run cost computed from response usage; a run
  aborts before the call that would exceed the cap.

Few-shot anchors from the golden set are added once the operator labels
golden/judge_candidates.csv (SPEC §7); v0 runs without anchors.
"""

import hashlib
import json
import os
import re

import anthropic

from src.classify import load_config
from src.envfile import load_env

# claude-sonnet-4-6 pricing, USD per token
PRICE_IN = 3.0 / 1e6
PRICE_OUT = 15.0 / 1e6
MAX_FIELD_CHARS = 2000

# Rubric iterations (SPEC §4 Phase 2 requires logging each):
#   v0   (2026-07-03): SPEC §7 core text verbatim.
#   v0.1 (2026-07-03): judge wrote prose deliberation on URI-only deliverables
#        and hit max_tokens before any JSON (job 1001773957, all 3 passes).
#        Added: JSON-must-be-entire-response constraint and explicit rule for
#        URI-only deliverables (score deliverable-kind match, note
#        unverifiable content in the reason).
SYSTEM = (
    "You are scoring whether a deliverable fulfills a job request. "
    "Score 0-10. 10 = fully addresses the request, correct format, internally "
    "consistent. 5 = partially addresses it or has format/consistency defects. "
    "0 = empty, unrelated, or contradicts the request. "
    "If the deliverable is only a URI/link, you cannot fetch it: score whether "
    "it is the right kind of deliverable for the request and say the content "
    "is unverifiable in the reason. "
    "Your ENTIRE response must be exactly one JSON object, starting with '{': "
    '{"score": <int 0-10>, "one_sentence_reason": "<reason>"}. '
    "No other text before or after."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS judge_scores (
    job_id      TEXT NOT NULL,
    prompt_sha  TEXT NOT NULL,
    pass_n      INTEGER NOT NULL,
    score       INTEGER,
    reason      TEXT,
    model       TEXT,
    in_tokens   INTEGER,
    out_tokens  INTEGER,
    raw_response TEXT,
    PRIMARY KEY (job_id, prompt_sha, pass_n)
);
"""


def strip_identity(text: str, agent_names: list[str]) -> str:
    text = re.sub(r"0x[0-9a-fA-F]{40}", "[ADDR]", text)
    for name in sorted(agent_names, key=len, reverse=True):
        if name:
            text = re.sub(re.escape(name), "[AGENT]", text, flags=re.I)
    return text


def judge_input(raw: dict, agent_names: list[str]) -> str | None:
    request = ""
    for m in raw.get("memos") or []:
        if m.get("type") == "REQUEST_JOB":
            request = m.get("content") or ""
            break
    if not request:
        request = raw.get("description") or ""
    deliverable = raw.get("deliverable")
    if deliverable in (None, "", {}):
        return None
    if not isinstance(deliverable, str):
        deliverable = json.dumps(deliverable, sort_keys=True)
    request = strip_identity(request, agent_names)[:MAX_FIELD_CHARS]
    deliverable = strip_identity(deliverable, agent_names)[:MAX_FIELD_CHARS]
    return f"<job_request>\n{request}\n</job_request>\n\n<deliverable>\n{deliverable}\n</deliverable>"


class Judge:
    def __init__(self, conn, config: dict = None):
        self.conn = conn
        conn.executescript(SCHEMA)
        cfg = (config or load_config())["judge"]
        self.model = cfg["model"]
        self.budget = float(cfg["budget_usd_per_run"])
        self.run_cost = 0.0
        self._client = None
        self.api_calls = 0

    @property
    def client(self):
        if self._client is None:
            load_env()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit("ANTHROPIC_API_KEY not set (load .env)")
            self._client = anthropic.Anthropic()
        return self._client

    def score(self, job_id: str, prompt: str, pass_n: int = 1) -> dict:
        sha = hashlib.sha256((SYSTEM + prompt).encode()).hexdigest()[:16]
        row = self.conn.execute(
            "SELECT score, reason FROM judge_scores WHERE job_id=? AND "
            "prompt_sha=? AND pass_n=?", (job_id, sha, pass_n)).fetchone()
        if row is not None:
            return {"score": row[0], "reason": row[1], "cached": True}

        # Budget guard: worst-case cost of the next call.
        est = (len(SYSTEM + prompt) / 3) * PRICE_IN + 200 * PRICE_OUT
        if self.run_cost + est > self.budget:
            raise RuntimeError(
                f"judge budget cap ${self.budget} would be exceeded "
                f"(spent ${self.run_cost:.2f}); aborting run")

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            temperature=0,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        self.api_calls += 1
        text = "".join(b.text for b in resp.content if b.type == "text")
        self.run_cost += (resp.usage.input_tokens * PRICE_IN
                          + resp.usage.output_tokens * PRICE_OUT)
        try:
            m = re.search(r"\{.*\}", text, re.S)
            parsed = json.loads(m.group(0))
            score = int(parsed["score"])
            reason = str(parsed.get("one_sentence_reason", ""))
            if not 0 <= score <= 10:
                raise ValueError(score)
        except Exception:
            score, reason = None, f"UNPARSEABLE: {text[:200]}"

        self.conn.execute(
            "INSERT OR REPLACE INTO judge_scores VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, sha, pass_n, score, reason, self.model,
             resp.usage.input_tokens, resp.usage.output_tokens, text))
        self.conn.commit()
        return {"score": score, "reason": reason, "cached": False}
