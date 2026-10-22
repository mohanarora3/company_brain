"""Ask: answers a successor's question from memory and live federated evidence.

1. H-MEM retrieval (hybrid ranking with a trace) over interview answers, tacit
   Slack answers, wiki sentences and verified findings.
2. A live federated look-up: Slack answers and wiki pages about the system the
   question is about, ranked by NVIDIA NIM embeddings (local vectors offline).
3. An answer that cites both, written by the LLM when one is configured, or
   extracted verbatim from the best evidence when not.

Every citation can be audited: memory ids open their H-MEM trust-ledger
history, Slack/wiki citations open the query that found them.
"""
from __future__ import annotations

from ..federation import Federation
from ..federation.base import in_list, lit
from ..llm.client import LLMError, get_llm
from ..llm.embeddings import get_embedder
from ..meterless.client import Meterless, MeterlessUnavailable
from .blackboard import Blackboard
from .investigators import Attributor

SYSTEM = ("You answer questions from an engineer taking over someone's work. Use only the numbered context. "
          "Cite every claim with its [n] marker. If the context does not answer the question, say what is missing "
          "and who to ask. Be concise: 2-5 sentences.")


def ask(fed: Federation, namespace: str, question: str, systems_meta: dict | None = None, directory: dict | None = None,
        as_of=None) -> dict:
    from datetime import date
    bb = Blackboard(fed, {"employee_id": "?"}, as_of or date.today())
    trace: list[dict] = []
    context: list[dict] = []

    # 1. Memory
    memory = {"available": False}
    try:
        m = Meterless(namespace)
        m.health()
        r = m.recall(question, top_n=12, threshold=0.08)
        memory = {"available": True, "trace": r["trace"]}
        # Numeric "claim" fragments exist so H-MEM's conflict detector can compare like with like;
        # they are not answers, so they stay out of the context a successor reads.
        hits = [x for x in r["memories"] if not x["memory"]["provenance"].get("label", "").startswith("Claim from")][:6]
        for x in hits:
            mem = x["memory"]
            context.append({"kind": "memory", "id": mem["id"], "text": mem["content"], "source": mem["source"],
                            "label": mem["provenance"].get("label", mem["source"]), "score": round(x["relevance"], 3),
                            "tags": mem["tags"]})
        trace.append({"step": "H-MEM retrieval", "detail": r["trace"]["retrievalReason"], "hits": len(hits)})
    except MeterlessUnavailable as e:
        trace.append({"step": "H-MEM retrieval", "detail": f"unavailable: {e}"})

    # 2. Live evidence
    systems = systems_meta or {}
    if not systems:
        res = bb.sql("Ask", "Load the service catalog", "SELECT system_id, name, aliases, description, slack_channel FROM github.service_catalog")
        for row in (res.rows if res else []):
            row["alias_list"] = [a.strip().lower() for a in (row.get("aliases") or "").split(",") if a.strip()]
            systems[row["system_id"]] = row
    attr = Attributor(systems)
    sysid, how = attr.best(question)
    live = []
    if sysid:
        s = systems[sysid]
        terms = [s["name"].lower()] + s.get("alias_list", [])
        like = " OR ".join(f"lower(text) LIKE {lit('%' + t + '%')}" for t in terms[:4])
        q = bb.sql("Ask", f"Slack answers about {s['name']}",
                   "SELECT ts, channel_name, user_id, text, created_at FROM slack.messages WHERE is_reply = 1 "
                   f"AND channel_name IN {in_list([s.get('slack_channel')])} AND length(text) > 60")
        roots = {}
        rows = q.rows if q else []
        if rows:
            r2 = bb.sql("Ask", "Thread questions", "SELECT ts, text FROM slack.messages WHERE is_reply = 0 "
                        f"AND channel_name IN {in_list([s.get('slack_channel')])} AND ({like})")
            roots = {x["ts"]: x["text"] for x in (r2.rows if r2 else [])}
        d = bb.sql("Ask", f"Wiki pages about {s['name']}",
                   f"SELECT page_id, title, body, updated_at FROM docs.pages WHERE {like.replace('text', 'body')}")
        users = bb.sql("Ask", "Slack names", "SELECT user_id, real_name FROM slack.users")
        names = {u["user_id"]: u["real_name"] for u in (users.rows if users else [])}
        seen = set()
        for row in rows:
            if row["text"] in seen:
                continue
            seen.add(row["text"])
            live.append({"kind": "slack", "id": f"slack:#{row['channel_name']}/{row['ts']}", "text": row["text"],
                         "label": f"{names.get(row['user_id'], row['user_id'])} in #{row['channel_name']}, {str(row['created_at'])[:10]}",
                         "question": roots.get(row.get("ts"))})
        for row in (d.rows if d else []):
            live.append({"kind": "doc", "id": f"docs:{row['page_id']}", "text": row["body"].split("\n\n", 2)[-1].strip(),
                         "label": f"Wiki: {row['title']} (updated {str(row['updated_at'])[:10]})"})
        if live:
            sims = get_embedder().similarity(question, [x["text"] for x in live])
            for x, sc in zip(live, sims):
                x["score"] = round(sc, 3)
            live.sort(key=lambda x: -x["score"])
            live = live[:5]
        trace.append({"step": "Federated search", "detail": f"system '{s['name']}' ({how}); {len(rows)} Slack answers and "
                      f"{len(d.rows) if d else 0} wiki pages ranked by {get_embedder().label}", "queries": [q.sql for q in bb.queries]})
    else:
        trace.append({"step": "Federated search", "detail": "no catalog system recognised in the question; memory only"})
    context += live

    # 3. Answer
    numbered = [{"n": i + 1, **c} for i, c in enumerate(context)]
    llm = get_llm()
    answer, mode = "", "extractive"
    if numbered and llm.enabled:
        try:
            ctx = "\n".join(f"[{c['n']}] ({c['label']}) {c['text']}" for c in numbered)
            answer = llm.chat(SYSTEM, f"Question: {question}\n\nContext:\n{ctx}", max_tokens=400)
            mode = llm.label
        except LLMError:
            answer = ""
    if not answer:
        if numbered:
            def rank(c: dict) -> float:
                # An exit-interview answer about the system in question outranks a Slack quote of similar relevance.
                tags = c.get("tags", [])
                bonus = 0.15 if c["kind"] == "memory" and "kind:interview" in tags and f"system:{sysid}" in tags else 0.0
                return (c.get("score") or 0) + bonus
            best = max(numbered, key=rank)
            answer = f"{best['text'].split('->')[-1].strip()} [{best['n']}]"
            mode = "extractive (no LLM key): best-ranked evidence, quoted"
        else:
            answer = "Nothing in memory or the connected systems answers this yet. Ask the departing owner in the exit interview."
    return {"question": question, "answer": answer, "mode": mode, "system": sysid, "context": numbered,
            "memory": memory, "trace": trace, "queries": [{"sql": q.sql, "rows": q.rows, "ms": q.ms, "engine": q.engine} for q in bb.queries]}
